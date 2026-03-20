"""
GitHub API Client - GraphQL + REST Hybrid.

Özellikler:
  • Singleton httpx.AsyncClient (connection pooling)
  • Rate-limit aware (X-RateLimit-* header okuma + akıllı bekleme)
  • Exponential backoff retry
  • Trending repo keşfi (çoklu dil)
  • Issue + Discussion çekme
  • Label filtreleme ("good first issue", "help wanted")
  • Yorum gönderme (Issue & Discussion)
  • Fork → Branch → Commit → PR pipeline
  • Git clone (shallow)
"""
import asyncio
import base64
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Optional

import httpx
from loguru import logger

from core.config import settings


class RateLimiter:
    """GitHub API rate-limit takipçisi."""

    def __init__(self):
        self.remaining: int = settings.GITHUB_MAX_REQUESTS_PER_HOUR
        self.reset_at: Optional[datetime] = None

    def update_from_headers(self, headers: dict):
        if "x-ratelimit-remaining" in headers:
            self.remaining = int(headers["x-ratelimit-remaining"])
        if "x-ratelimit-reset" in headers:
            self.reset_at = datetime.fromtimestamp(int(headers["x-ratelimit-reset"]))

    async def wait_if_needed(self):
        if self.remaining <= 50 and self.reset_at:
            wait = (self.reset_at - datetime.now()).total_seconds()
            if wait > 0:
                logger.warning(f"⏳ Rate limit düşük ({self.remaining}). {wait:.0f}s bekleniyor...")
                await asyncio.sleep(min(wait + 2, 900))  # max 15 dk


class GitHubGraphQLClient:
    """
    Tekil HTTP client ile GitHub GraphQL + REST API etkileşimi.
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._rate_limiter = RateLimiter()

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Retry wrapper ─────────────────────────────────────────
    async def _request_with_retry(self, method: str, url: str, **kwargs) -> Optional[httpx.Response]:
        client = await self._get_client()
        last_exc = None

        for attempt in range(1, settings.GITHUB_RETRY_MAX_ATTEMPTS + 1):
            try:
                await self._rate_limiter.wait_if_needed()
                resp = await client.request(method, url, **kwargs)
                self._rate_limiter.update_from_headers(dict(resp.headers))

                if resp.status_code == 403 and "rate limit" in resp.text.lower():
                    logger.warning(f"Rate limit 403 alındı, bekleniyor... (attempt {attempt})")
                    await asyncio.sleep(60)
                    continue

                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                return resp
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as e:
                last_exc = e
                delay = settings.GITHUB_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(f"GitHub isteği başarısız (attempt {attempt}): {e}. {delay}s sonra tekrar...")
                await asyncio.sleep(delay)

        logger.error(f"GitHub isteği {settings.GITHUB_RETRY_MAX_ATTEMPTS} denemede de başarısız: {last_exc}")
        return None

    # ── GraphQL ────────────────────────────────────────────────
    async def execute_graphql(self, query: str, variables: dict = None) -> Optional[dict]:
        if not settings.GITHUB_TOKEN:
            logger.error("GITHUB_TOKEN ayarlanmamış! .env dosyasını kontrol edin.")
            return None

        resp = await self._request_with_retry(
            "POST", "https://api.github.com/graphql",
            json={"query": query, "variables": variables or {}},
        )
        if resp is None:
            return None

        result = resp.json()
        if "errors" in result:
            logger.error(f"GraphQL hataları: {result['errors']}")
        return result

    # ── REST Helper ────────────────────────────────────────────
    async def _rest_get(self, path: str, params: dict = None) -> Optional[dict]:
        resp = await self._request_with_retry("GET", f"https://api.github.com{path}", params=params)
        if resp and resp.status_code == 200:
            return resp.json()
        return None

    async def _rest_post(self, path: str, json_data: dict = None) -> Optional[httpx.Response]:
        return await self._request_with_retry("POST", f"https://api.github.com{path}", json=json_data)

    async def _rest_put(self, path: str, json_data: dict = None) -> Optional[httpx.Response]:
        return await self._request_with_retry("PUT", f"https://api.github.com{path}", json=json_data)

    # ══════════════════════════════════════════════════════════
    #  TRENDING REPO KEŞFİ
    # ══════════════════════════════════════════════════════════

    async def fetch_trending_repos(
        self,
        language: str = "Python",
        limit: int = 5,
        days_ago: int = 7,
        min_stars: int = 50,
    ) -> list[dict]:
        """Belirtilen dil ve zaman aralığında en popüler repoları çeker."""
        query = """
        query SearchTrendingRepos($queryString: String!, $first: Int!) {
          search(query: $queryString, type: REPOSITORY, first: $first) {
            nodes {
              ... on Repository {
                name
                owner { login }
                url
                description
                stargazerCount
                primaryLanguage { name }
                defaultBranchRef { name }
                repositoryTopics(first: 10) {
                  nodes { topic { name } }
                }
                issues(states: OPEN) { totalCount }
                createdAt
                updatedAt
                hasIssuesEnabled
                hasDiscussionsEnabled
              }
            }
          }
        }
        """
        date_threshold = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        query_string = f"language:{language} created:>{date_threshold} stars:>={min_stars} sort:stars-desc"

        data = await self.execute_graphql(query, {"queryString": query_string, "first": limit})
        if data and "data" in data and "search" in data["data"]:
            return data["data"]["search"]["nodes"]
        return []

    async def fetch_trending_all_languages(self) -> list[dict]:
        """Tüm hedef dillerde trending repoları çeker, Python'a ağırlık verir."""
        all_repos = []
        for lang in settings.TARGET_LANGUAGES:
            limit = (
                settings.TRENDING_LIMIT_PER_LANGUAGE * 2
                if lang == settings.PRIMARY_LANGUAGE
                else settings.TRENDING_LIMIT_PER_LANGUAGE
            )
            repos = await self.fetch_trending_repos(
                language=lang,
                limit=limit,
                days_ago=settings.TRENDING_DAYS_AGO,
                min_stars=settings.MIN_STARS_THRESHOLD,
            )
            for r in repos:
                r["_search_language"] = lang
            all_repos.extend(repos)
            # Diller arası kısa bekleme
            await asyncio.sleep(0.5)
        return all_repos

    # ══════════════════════════════════════════════════════════
    #  ISSUE İŞLEMLERİ
    # ══════════════════════════════════════════════════════════

    async def fetch_repo_issues(
        self,
        owner: str,
        name: str,
        limit: int = 10,
        labels: list[str] = None,
    ) -> list[dict]:
        """Bir reponun açık issue'larını çeker, isteğe bağlı label filtreleme ile."""
        query = """
        query GetRepoIssues($owner: String!, $name: String!, $first: Int!, $labels: [String!]) {
          repository(owner: $owner, name: $name) {
            issues(first: $first, states: OPEN, labels: $labels, orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                number
                title
                body
                url
                createdAt
                comments { totalCount }
                labels(first: 10) {
                  nodes { name }
                }
              }
            }
          }
        }
        """
        variables: dict = {"owner": owner, "name": name, "first": limit}
        if labels:
            variables["labels"] = labels

        data = await self.execute_graphql(query, variables)
        if data and "data" in data:
            repo_data = data["data"].get("repository")
            if repo_data:
                return repo_data["issues"]["nodes"]
        return []

    async def post_issue_comment(self, owner: str, name: str, issue_number: int, body: str) -> Optional[str]:
        """Issue'ya yorum gönderir, yorum URL'sini döndürür."""
        resp = await self._rest_post(
            f"/repos/{owner}/{name}/issues/{issue_number}/comments",
            json_data={"body": body},
        )
        if resp and resp.status_code == 201:
            url = resp.json().get("html_url")
            logger.success(f"Issue #{issue_number} yorumu gönderildi: {url}")
            return url
        logger.error(f"Issue yorum gönderilemedi: {resp.text if resp else 'Yanıt yok'}")
        return None

    # ══════════════════════════════════════════════════════════
    #  DISCUSSION İŞLEMLERİ
    # ══════════════════════════════════════════════════════════

    async def fetch_repo_discussions(self, owner: str, name: str, limit: int = 5) -> list[dict]:
        """Bir reponun cevaplanmamış discussion'larını çeker."""
        query = """
        query GetDiscussions($owner: String!, $name: String!, $first: Int!) {
          repository(owner: $owner, name: $name) {
            discussions(first: $first, orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                number
                id
                title
                body
                url
                createdAt
                category { name }
                comments { totalCount }
                answer { id }
              }
            }
          }
        }
        """
        data = await self.execute_graphql(query, {"owner": owner, "name": name, "first": limit})
        if data and "data" in data:
            repo_data = data["data"].get("repository")
            if repo_data and "discussions" in repo_data:
                return repo_data["discussions"]["nodes"]
        return []

    async def post_discussion_comment(self, discussion_node_id: str, body: str) -> Optional[str]:
        """Discussion'a yorum ekler (GraphQL Mutation)."""
        mutation = """
        mutation AddDiscussionComment($discussionId: ID!, $body: String!) {
          addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
            comment {
              id
              url
            }
          }
        }
        """
        data = await self.execute_graphql(mutation, {
            "discussionId": discussion_node_id,
            "body": body,
        })
        if data and "data" in data:
            comment_data = data["data"].get("addDiscussionComment", {}).get("comment")
            if comment_data:
                logger.success(f"Discussion yorumu gönderildi: {comment_data['url']}")
                return comment_data["url"]
        logger.error(f"Discussion yorum gönderilemedi: {data}")
        return None

    # ══════════════════════════════════════════════════════════
    #  FORK → BRANCH → COMMIT → PR PİPELINE
    # ══════════════════════════════════════════════════════════

    async def get_authenticated_user(self) -> Optional[str]:
        data = await self._rest_get("/user")
        return data.get("login") if data else None

    async def fork_repository(self, owner: str, name: str) -> Optional[dict]:
        resp = await self._rest_post(f"/repos/{owner}/{name}/forks")
        if resp and resp.status_code in [201, 202]:
            logger.success(f"Repo fork edildi: {owner}/{name}")
            return resp.json()
        logger.error(f"Fork başarısız: {resp.text if resp else 'Yanıt yok'}")
        return None

    async def get_repo_default_branch(self, owner: str, name: str) -> Optional[str]:
        data = await self._rest_get(f"/repos/{owner}/{name}")
        return data.get("default_branch") if data else None

    async def get_repo_base_sha(self, owner: str, name: str, branch: str = "main") -> Optional[str]:
        data = await self._rest_get(f"/repos/{owner}/{name}/git/ref/heads/{branch}")
        return data.get("object", {}).get("sha") if data else None

    async def create_branch(self, owner: str, name: str, branch_name: str, base_sha: str) -> bool:
        resp = await self._rest_post(
            f"/repos/{owner}/{name}/git/refs",
            json_data={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        return resp is not None and resp.status_code == 201

    async def update_file(
        self, owner: str, name: str, path: str, content: str,
        message: str, branch: str,
    ) -> bool:
        """Dosyayı commit eder (yoksa oluşturur, varsa günceller)."""
        url = f"/repos/{owner}/{name}/contents/{path}"
        # Mevcut dosyanın SHA'sını al (retry wrapper ile)
        existing = await self._rest_get(url, params={"ref": branch})
        sha = existing.get("sha") if existing else None

        encoded = base64.b64encode(content.encode()).decode()
        body = {"message": message, "content": encoded, "branch": branch}
        if sha:
            body["sha"] = sha

        resp = await self._rest_put(url, json_data=body)
        return resp is not None and resp.status_code in [200, 201]

    async def create_pull_request(
        self,
        original_owner: str, name: str,
        title: str, body: str,
        head_branch: str, base_branch: str = "main",
    ) -> Optional[str]:
        user_login = await self.get_authenticated_user()
        if not user_login:
            logger.error("PR açılamıyor: kullanıcı bilgisi alınamadı.")
            return None

        resp = await self._rest_post(
            f"/repos/{original_owner}/{name}/pulls",
            json_data={
                "title": title,
                "body": body,
                "head": f"{user_login}:{head_branch}",
                "base": base_branch,
            },
        )
        if resp and resp.status_code == 201:
            pr_url = resp.json().get("html_url")
            logger.success(f"PR açıldı: {pr_url}")
            return pr_url
        logger.error(f"PR açılamadı: {resp.text if resp else 'Yanıt yok'}")
        return None

    # ══════════════════════════════════════════════════════════
    #  REPO KLONLAMA
    # ══════════════════════════════════════════════════════════

    async def clone_repo(self, owner: str, name: str, target_dir: str = None) -> Optional[str]:
        """
        Repoyu shallow clone yapar. Zaten varsa günceller.
        Returns: klonlanan dizin yolu.
        """
        if target_dir is None:
            target_dir = os.path.join(settings.WORKSPACE_DIR, f"{owner}__{name}")

        repo_url = f"https://github.com/{owner}/{name}.git"

        try:
            if os.path.exists(os.path.join(target_dir, ".git")):
                logger.info(f"Repo zaten klonlanmış, güncelleniyor: {target_dir}")
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", target_dir, "pull", "--depth=1"],
                    capture_output=True, text=True, timeout=120,
                )
            else:
                os.makedirs(target_dir, exist_ok=True)
                logger.info(f"Repo klonlanıyor: {repo_url} → {target_dir}")
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "clone", "--depth=1", repo_url, target_dir],
                    capture_output=True, text=True, timeout=120,
                )

            if proc.returncode != 0:
                logger.error(f"Git hatası: {proc.stderr}")
                return None

            logger.success(f"Repo klonlandı: {target_dir}")
            return target_dir

        except subprocess.TimeoutExpired:
            logger.error(f"Git clone zaman aşımı: {owner}/{name}")
            return None
        except FileNotFoundError:
            logger.error("Git bulunamadı! PATH'te 'git' yüklü olmalı.")
            return None

    async def delete_clone(self, clone_path: str):
        """Klonlanan repo dizinini siler."""
        if clone_path and os.path.exists(clone_path):
            await asyncio.to_thread(shutil.rmtree, clone_path, ignore_errors=True)
            logger.info(f"Klon silindi: {clone_path}")

