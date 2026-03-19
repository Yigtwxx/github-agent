"""
Agent Orchestrator - Otonom GitHub katkı ajanının merkez beyni.

Pipeline:
  1. TREND HUNT     → Çoklu dilde popüler repoları keşfet, skorla, DB'ye kaydet
  2. REPO SETUP     → En yüksek skorlu repoları klonla, RAG'a indeksle
  3. COMMUNITY      → Issue'lara yardımcı cevaplar üret → onaya sun
  4. DISCUSSIONS     → Discussion'lara cevap üret → onaya sun
  5. ISSUE SOLVING   → Çözülebilir issue'ları bul → kod üret → Docker'da test → PR onaya sun
  6. PR PIPELINE    → Onaylanan kod değişikliklerini fork → branch → commit → PR

Tüm operasyonlar async, paralel repo işleme destekli.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from agent.tools.github_client import GitHubGraphQLClient
from agent.tools.ollama_client import OllamaAIClient
from agent.tools.chroma_client import ChromaDBManager
from agent.tools.docker_env import DockerSandbox
from core.config import settings
from database.session import SessionLocal
from database.models import (
    Repo, Issue, Discussion, AgentActionHistory,
    AgentComment, CodePatch,
)


class AgentOrchestrator:
    """Otonom GitHub Agent - Ana orkestratör."""

    def __init__(self):
        self.status = "IDLE"
        self.is_running = False
        self.stats = {
            "cycles_completed": 0,
            "repos_discovered": 0,
            "issues_analyzed": 0,
            "discussions_analyzed": 0,
            "prs_created": 0,
            "comments_generated": 0,
        }
        # Tool bileşenleri
        self.github = GitHubGraphQLClient()
        self.ai = OllamaAIClient()
        self.rag = ChromaDBManager()
        self.sandbox = DockerSandbox()

    # ══════════════════════════════════════════════════════════
    #  ANA DÖNGÜ
    # ══════════════════════════════════════════════════════════

    async def run_autonomous_loop(self):
        """
        Sonsuz otonom döngü.
        Her iterasyonda: keşfet → kurulum → topluluk → discussion → issue çöz
        """
        self.is_running = True
        self.status = "RUNNING"
        logger.info("═══════════════════════════════════════════")
        logger.info("  🤖 Otonom GitHub Agent başlatıldı")
        logger.info(f"  📋 Hedef diller: {settings.TARGET_LANGUAGES}")
        logger.info(f"  🧠 AI Model: {settings.OLLAMA_MODEL}")
        logger.info(f"  ⏰ Döngü aralığı: {settings.LOOP_INTERVAL_SECONDS}s")
        logger.info("═══════════════════════════════════════════")

        while self.is_running:
            try:
                self.status = "TREND_HUNT"
                await self._phase_trend_hunt()

                self.status = "REPO_SETUP"
                await self._phase_repo_setup()

                self.status = "COMMUNITY_SUPPORT"
                await self._phase_community_support()

                self.status = "DISCUSSION_REPLY"
                await self._phase_discussion_support()

                self.status = "ISSUE_SOLVING"
                await self._phase_issue_solving()

                self.stats["cycles_completed"] += 1
                self.status = "SLEEPING"
                logger.info(
                    f"✅ Döngü #{self.stats['cycles_completed']} tamamlandı. "
                    f"Sonraki döngü: {settings.LOOP_INTERVAL_SECONDS}s sonra"
                )
                await asyncio.sleep(settings.LOOP_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                logger.info("Agent döngüsü iptal edildi.")
                break
            except Exception as e:
                logger.error(f"Döngüde beklenmeyen hata: {e}")
                self.status = "ERROR_RECOVERY"
                await asyncio.sleep(settings.ERROR_RETRY_DELAY_SECONDS)

        self.status = "STOPPED"
        await self.github.close()

    # ══════════════════════════════════════════════════════════
    #  PHASE 1: TREND HUNT - Popüler repo keşfi
    # ══════════════════════════════════════════════════════════

    async def _phase_trend_hunt(self):
        logger.info("━━━ Phase 1: Trend Hunt ━━━")
        repos = await self.github.fetch_trending_all_languages()

        if not repos:
            logger.warning("Trending repo bulunamadı.")
            return

        db = SessionLocal()
        try:
            for repo_data in repos:
                owner = repo_data.get("owner", {}).get("login", "")
                name = repo_data.get("name", "")
                if not owner or not name:
                    continue

                # Zaten var mı?
                def check_repo():
                    return db.query(Repo).filter(
                        Repo.owner == owner, Repo.name == name
                    ).first()
                existing = await asyncio.to_thread(check_repo)
                if existing:
                    # Star güncelle
                    def update_existing():
                        existing.stars = repo_data.get("stargazerCount", existing.stars)
                        existing.last_checked_at = datetime.now(timezone.utc)
                        db.commit()
                    await asyncio.to_thread(update_existing)
                    continue

                # Yeni repo kaydet
                primary_lang = repo_data.get("primaryLanguage")
                default_branch_ref = repo_data.get("defaultBranchRef")
                topics_data = repo_data.get("repositoryTopics", {}).get("nodes", [])
                topics = [t["topic"]["name"] for t in topics_data] if topics_data else []
                open_issues = repo_data.get("issues", {}).get("totalCount", 0)

                new_repo = Repo(
                    owner=owner,
                    name=name,
                    url=repo_data.get("url", ""),
                    description=repo_data.get("description", ""),
                    stars=repo_data.get("stargazerCount", 0),
                    language=primary_lang["name"] if primary_lang else None,
                    default_branch=default_branch_ref["name"] if default_branch_ref else "main",
                    topics=topics,
                    open_issue_count=open_issues,
                    is_trending=True,
                    priority_score=self._calculate_priority(repo_data),
                )
                def commit_new_repo():
                    db.add(new_repo)
                    db.commit()
                    db.refresh(new_repo)
                await asyncio.to_thread(commit_new_repo)

                self.stats["repos_discovered"] += 1
                logger.success(
                    f"  ✨ Yeni repo: {owner}/{name} "
                    f"(⭐{new_repo.stars} | 📋{open_issues} issues | "
                    f"🎯{new_repo.priority_score:.1f})"
                )

                # Aksiyon kaydı
                def add_action():
                    new_action = AgentActionHistory(
                        repo_id=new_repo.id,
                        action_type="TREND_HUNT",
                        status="SUCCESS",
                        details={"stars": new_repo.stars, "language": new_repo.language},
                    )
                    db.add(new_action)
                    db.commit()
                await asyncio.to_thread(add_action)

        except Exception as e:
            logger.error(f"Trend hunt DB hatası: {e}")
            db.rollback()
        finally:
            db.close()

    def _calculate_priority(self, repo_data: dict) -> float:
        """Repo öncelik skoru hesapla (0-100)."""
        score = 0.0
        stars = repo_data.get("stargazerCount", 0)
        open_issues = repo_data.get("issues", {}).get("totalCount", 0)
        has_discussions = repo_data.get("hasDiscussionsEnabled", False)

        # Star skoru (max 40)
        if stars >= 1000:
            score += 40
        elif stars >= 500:
            score += 30
        elif stars >= 100:
            score += 20
        else:
            score += 10

        # Issue skoru (max 30)
        if open_issues >= 20:
            score += 30
        elif open_issues >= 10:
            score += 25
        elif open_issues >= 5:
            score += 15
        else:
            score += 5

        # Discussion desteği (max 15)
        if has_discussions:
            score += 15

        # Dil bonus (Python ağırlıklı) (max 15)
        lang = repo_data.get("primaryLanguage", {})
        lang_name = lang.get("name", "") if lang else ""
        if lang_name == "Python":
            score += 15
        elif lang_name in ("TypeScript", "JavaScript"):
            score += 10
        elif lang_name in ("Go", "Rust"):
            score += 8
        else:
            score += 3

        return min(score, 100.0)

    # ══════════════════════════════════════════════════════════
    #  PHASE 2: REPO SETUP - Klonla + RAG indeksle
    # ══════════════════════════════════════════════════════════

    async def _phase_repo_setup(self):
        logger.info("━━━ Phase 2: Repo Setup ━━━")
        db = SessionLocal()
        try:
            # RAG'a henüz indekslenmemiş en yüksek skorlu repolar
            def get_repos_to_setup():
                return (
                    db.query(Repo)
                    .filter(Repo.rag_indexed == False, Repo.is_trending == True)
                    .order_by(Repo.priority_score.desc())
                    .limit(settings.TASK_CONCURRENCY)
                    .all()
                )
            repos = await asyncio.to_thread(get_repos_to_setup)

            if not repos:
                logger.info("  Tüm repolar zaten indekslenmiş.")
                return

            for repo in repos:
                try:
                    # Klonla
                    await asyncio.sleep(0.01)  # Yield event loop
                    clone_path = await self.github.clone_repo(repo.owner, repo.name)
                    if not clone_path:
                        continue

                    repo.cloned_path = clone_path

                    # RAG indeksle
                    chunk_count = await asyncio.to_thread(
                        self.rag.index_repository,
                        f"{repo.owner}/{repo.name}",
                        clone_path,
                    )
                    repo.rag_indexed = True
                    db.commit()

                    logger.success(
                        f"  📚 {repo.owner}/{repo.name}: klonlandı + "
                        f"{chunk_count} chunk indekslendi"
                    )
                except Exception as e:
                    logger.error(f"  Repo setup hatası ({repo.owner}/{repo.name}): {e}")
                    continue

        except Exception as e:
            logger.error(f"Phase 2 hatası: {e}")
            db.rollback()
        finally:
            db.close()

    # ══════════════════════════════════════════════════════════
    #  PHASE 3: COMMUNITY SUPPORT - Issue'lara cevap üret
    # ══════════════════════════════════════════════════════════

    async def _phase_community_support(self):
        logger.info("━━━ Phase 3: Community Support ━━━")
        db = SessionLocal()
        try:
            def get_trending_repos():
                return (
                    db.query(Repo)
                    .filter(Repo.is_trending == True)
                    .order_by(Repo.priority_score.desc())
                    .limit(settings.TASK_CONCURRENCY)
                    .all()
                )
            repos = await asyncio.to_thread(get_trending_repos)

            for repo in repos:
                await self._process_repo_issues(db, repo)

        except Exception as e:
            logger.error(f"Phase 3 hatası: {e}")
            db.rollback()
        finally:
            db.close()

    async def _process_repo_issues(self, db, repo: Repo):
        """Tek bir repo'nun issue'larını işle."""
        issues = await self.github.fetch_repo_issues(
            owner=repo.owner,
            name=repo.name,
            limit=settings.ISSUES_PER_REPO,
        )

        for issue_data in issues:
            issue_number = issue_data.get("number")
            if not issue_number:
                continue

            # DB'de var mı?
            def check_issue():
                return db.query(Issue).filter(
                    Issue.repo_id == repo.id,
                    Issue.issue_number == issue_number,
                ).first()
            existing = await asyncio.to_thread(check_issue)
            if existing:
                continue

            # Issue'yu kaydet
            labels = [l["name"] for l in issue_data.get("labels", {}).get("nodes", [])]
            comments_count = issue_data.get("comments", {}).get("totalCount", 0)

            new_issue = Issue(
                repo_id=repo.id,
                issue_number=issue_number,
                title=issue_data.get("title", ""),
                body=issue_data.get("body", ""),
                state="OPEN",
                url=issue_data.get("url", ""),
                labels=labels,
                comment_count=comments_count,
                is_good_first_issue="good first issue" in labels,
                created_at=issue_data.get("createdAt"),
            )
            def save_new_issue():
                db.add(new_issue)
                db.commit()
                db.refresh(new_issue)
            await asyncio.to_thread(save_new_issue)

            # --- RAG bağlamı al ---
            repo_full = f"{repo.owner}/{repo.name}"
            query_text = f"{new_issue.title} {new_issue.body or ''}"[:500]
            rag_results = await asyncio.to_thread(
                self.rag.query_relevant_code,
                query_text=query_text,
                repo_full_name=repo_full,
                n_results=3,
            )
            context_str = "\n---\n".join([
                f"[{r['file_path']}]\n```{r['language']}\n{r['text']}\n```"
                for r in rag_results
            ]) if rag_results else ""

            # --- AI cevap üret ---
            logger.info(f"  💬 AI analiz: Issue #{issue_number} → {new_issue.title[:60]}")
            result = await self.ai.analyze_issue_for_support(
                issue_title=new_issue.title,
                issue_body=new_issue.body or "",
                repo_context=context_str,
            )

            if result["status"] == "success":
                # Onay bekleyen yorum olarak kaydet
                comment = AgentComment(
                    repo_id=repo.id,
                    target_type="ISSUE",
                    target_number=issue_number,
                    target_url=new_issue.url,
                    body=result["reply"],
                    status="AWAITING_APPROVAL",
                )
                def save_comment():
                    db.add(comment)
                    db.commit()
                await asyncio.to_thread(save_comment)

                self.stats["comments_generated"] += 1
                logger.success(
                    f"  ✅ Yorum üretildi (ONAY BEKLİYOR) → Issue #{issue_number}"
                )
            else:
                logger.warning(f"  ⚠️ AI Issue #{issue_number} için cevap üretemedi")

            self.stats["issues_analyzed"] += 1
            def update_analyzed_at():
                new_issue.analyzed_at = datetime.now(timezone.utc)
                db.commit()
            await asyncio.to_thread(update_analyzed_at)

            await asyncio.sleep(1)  # API & AI arası nefes alma

    # ══════════════════════════════════════════════════════════
    #  PHASE 4: DISCUSSION SUPPORT
    # ══════════════════════════════════════════════════════════

    async def _phase_discussion_support(self):
        logger.info("━━━ Phase 4: Discussion Support ━━━")
        db = SessionLocal()
        try:
            def get_trending_repos_for_discussions():
                return (
                    db.query(Repo)
                    .filter(Repo.is_trending == True)
                    .order_by(Repo.priority_score.desc())
                    .limit(settings.TASK_CONCURRENCY)
                    .all()
                )
            repos = await asyncio.to_thread(get_trending_repos_for_discussions)

            for repo in repos:
                await self._process_repo_discussions(db, repo)

        except Exception as e:
            logger.error(f"Phase 4 hatası: {e}")
            db.rollback()
        finally:
            db.close()

    async def _process_repo_discussions(self, db, repo: Repo):
        """Tek bir repo'nun discussion'larını işle."""
        discussions = await self.github.fetch_repo_discussions(
            owner=repo.owner,
            name=repo.name,
            limit=settings.DISCUSSIONS_PER_REPO,
        )

        for disc_data in discussions:
            disc_number = disc_data.get("number")
            if not disc_number:
                continue

            # Zaten cevaplanmış mı?
            if disc_data.get("answer"):
                continue

            # DB'de var mı?
            def check_discussion():
                return db.query(Discussion).filter(
                    Discussion.repo_id == repo.id,
                    Discussion.discussion_number == disc_number,
                ).first()
            existing = await asyncio.to_thread(check_discussion)
            if existing:
                continue

            category_data = disc_data.get("category", {})
            new_disc = Discussion(
                repo_id=repo.id,
                discussion_number=disc_number,
                node_id=disc_data.get("id", ""),
                title=disc_data.get("title", ""),
                body=disc_data.get("body", ""),
                category=category_data.get("name", "") if category_data else "",
                url=disc_data.get("url", ""),
                answer_count=disc_data.get("comments", {}).get("totalCount", 0),
                is_answered=disc_data.get("answer") is not None,
                created_at=disc_data.get("createdAt"),
            )
            def save_new_disc():
                db.add(new_disc)
                db.commit()
                db.refresh(new_disc)
            await asyncio.to_thread(save_new_disc)

            # RAG bağlamı
            repo_full = f"{repo.owner}/{repo.name}"
            rag_results = await asyncio.to_thread(
                self.rag.query_relevant_code,
                query_text=f"{new_disc.title} {new_disc.body or ''}"[:500],
                repo_full_name=repo_full,
                n_results=3,
            )
            context_str = "\n---\n".join([
                f"[{r['file_path']}]\n```{r['language']}\n{r['text']}\n```"
                for r in rag_results
            ]) if rag_results else ""

            # AI cevap üret
            logger.info(f"  💬 AI analiz: Discussion #{disc_number} → {new_disc.title[:60]}")
            result = await self.ai.generate_discussion_reply(
                discussion_title=new_disc.title,
                discussion_body=new_disc.body or "",
                category=new_disc.category or "",
                repo_context=context_str,
            )

            if result["status"] == "success":
                comment = AgentComment(
                    repo_id=repo.id,
                    target_type="DISCUSSION",
                    target_number=disc_number,
                    target_node_id=new_disc.node_id,
                    target_url=new_disc.url,
                    body=result["reply"],
                    status="AWAITING_APPROVAL",
                )
                def save_disc_comment():
                    db.add(comment)
                    db.commit()
                await asyncio.to_thread(save_disc_comment)

                self.stats["comments_generated"] += 1
                logger.success(f"  ✅ Discussion cevabı üretildi (ONAY BEKLİYOR) → #{disc_number}")
            else:
                logger.warning(f"  ⚠️ AI Discussion #{disc_number} için cevap üretemedi")

            self.stats["discussions_analyzed"] += 1
            def update_disc_analyzed():
                new_disc.analyzed_at = datetime.now(timezone.utc)
                db.commit()
            await asyncio.to_thread(update_disc_analyzed)

            await asyncio.sleep(1)

    # ══════════════════════════════════════════════════════════
    #  PHASE 5: ISSUE SOLVING - Gerçek kod üretimi + test
    # ══════════════════════════════════════════════════════════

    async def _phase_issue_solving(self):
        logger.info("━━━ Phase 5: Issue Solving ━━━")
        db = SessionLocal()
        try:
            # Çözülebilirlik analizi yapılmamış issue'ları bul
            def get_unsolved_issues():
                return (
                    db.query(Issue)
                    .join(Repo)
                    .filter(
                        Issue.state == "OPEN",
                        Issue.ai_solvability == None,
                        Repo.rag_indexed == True,
                    )
                    .order_by(Repo.priority_score.desc())
                    .limit(settings.TASK_CONCURRENCY)
                    .all()
                )
            issues = await asyncio.to_thread(get_unsolved_issues)

            for issue in issues:
                def get_issue_repo():
                    return db.query(Repo).filter(Repo.id == issue.repo_id).first()
                repo = await asyncio.to_thread(get_issue_repo)
                if not repo:
                    continue
                await asyncio.sleep(0.01)
                await self._analyze_and_solve_issue(db, repo, issue)

        except Exception as e:
            logger.error(f"Phase 5 hatası: {e}")
            db.rollback()
        finally:
            db.close()

    async def _analyze_and_solve_issue(self, db, repo: Repo, issue: Issue):
        """Tek bir issue'yu analiz et, çözülebilirse kod üret ve test et."""
        repo_full = f"{repo.owner}/{repo.name}"

        # 1. RAG ile ilgili dosyaları bul
        query = f"{issue.title} {issue.body or ''}"[:500]
        rag_results = await asyncio.to_thread(
            self.rag.query_relevant_code,
            query_text=query, repo_full_name=repo_full, n_results=5
        )
        context_str = "\n---\n".join([
            f"[{r['file_path']}]\n```{r['language']}\n{r['text']}\n```"
            for r in rag_results
        ]) if rag_results else ""

        # 2. Çözülebilirlik analizi
        logger.info(f"  🔍 Solvability analizi: Issue #{issue.issue_number} → {issue.title[:60]}")
        analysis = await self.ai.analyze_issue_solvability(
            issue_title=issue.title,
            issue_body=issue.body or "",
            labels=issue.labels or [],
            repo_context=context_str,
        )

        if not analysis:
            def skip_issue():
                issue.ai_solvability = "SKIP"
                db.commit()
            await asyncio.to_thread(skip_issue)
            return

        solvability = analysis.get("solvability", "SKIP")
        difficulty = analysis.get("difficulty", 10)
        issue.ai_solvability = solvability
        issue.ai_difficulty_score = float(difficulty)
        issue.analyzed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            f"  📊 Analiz sonucu: {solvability} (zorluk: {difficulty}/10)"
        )

        # Sadece SOLVABLE ve zorluk <= 6 olanları çöz
        if solvability != "SOLVABLE" or difficulty > 6:
            logger.info(f"  ⏭️ Issue #{issue.issue_number} atlanıyor ({solvability}, zorluk={difficulty})")
            return

        # 3. İlgili dosya içeriklerini oku
        file_contents = {}
        estimated_files = analysis.get("estimated_files", [])

        if repo.cloned_path and os.path.exists(repo.cloned_path):
            for fp in estimated_files[:5]:  # max 5 dosya
                content = self.rag.get_file_content_from_clone(repo.cloned_path, fp)
                if content:
                    file_contents[fp] = content

        # RAG'dan bulunan dosyaları da ekle
        for r in rag_results:
            fp = r["file_path"]
            if fp not in file_contents and repo.cloned_path:
                content = self.rag.get_file_content_from_clone(repo.cloned_path, fp)
                if content:
                    file_contents[fp] = content

        if not file_contents:
            logger.warning(f"  ⚠️ İlgili dosya içerikleri okunamadı, atlanıyor.")
            issue.ai_solvability = "NEEDS_INFO"
            db.commit()
            return

        # 4. Kod fix üret
        logger.info(f"  🔧 Kod fix üretiliyor... ({len(file_contents)} dosya bağlamında)")
        fix_result = await self.ai.generate_code_fix(
            issue_title=issue.title,
            issue_body=issue.body or "",
            file_contents=file_contents,
            suggested_approach=analysis.get("suggested_approach", ""),
        )

        if not fix_result or "changes" not in fix_result:
            logger.warning(f"  ⚠️ Kod fix üretilemedi")
            return

        changes = fix_result.get("changes", [])
        if not changes:
            return

        # 5. Syntax kontrolü
        all_valid = True
        for change in changes:
            fp = change.get("file_path", "")
            if fp.endswith(".py"):
                lint = await self.sandbox.lint_python_file(change.get("new_content", ""))
                if not lint["valid"]:
                    logger.warning(f"  ⚠️ Syntax hatası ({fp}): {lint['error']}")
                    all_valid = False

        if not all_valid:
            logger.warning(f"  ⚠️ Syntax hataları var, atlanıyor.")
            return

        # 6. Docker sandbox testi (opsiyonel)
        sandbox_passed = None
        sandbox_logs = ""
        if self.sandbox.available and repo.cloned_path:
            logger.info(f"  🐳 Docker sandbox testi çalıştırılıyor...")
            test_result = await self.sandbox.run_tests(repo.cloned_path)
            sandbox_passed = test_result["status"] == "success"
            sandbox_logs = test_result.get("logs", "")[:3000]

        # 7. Onay bekleyen aksiyon oluştur
        commit_msg = fix_result.get("commit_message", f"fix: resolve issue #{issue.issue_number}")
        branch_name = f"ai-fix/issue-{issue.issue_number}"

        action = AgentActionHistory(
            repo_id=repo.id,
            action_type="ISSUE_SOLVING",
            status="AWAITING_APPROVAL",
            issue_id=issue.id,
            proposed_branch=branch_name,
            commit_message=commit_msg,
            sandbox_test_passed=sandbox_passed,
            sandbox_test_logs=sandbox_logs,
            details={
                "issue_url": issue.url,
                "difficulty": difficulty,
                "changes_summary": fix_result.get("summary", ""),
                "files_changed": [c["file_path"] for c in changes],
            },
        )
        db.add(action)
        db.commit()
        db.refresh(action)

        # Kod patch'lerini kaydet
        for change in changes:
            original = file_contents.get(change["file_path"], "")
            patch = CodePatch(
                action_id=action.id,
                file_path=change["file_path"],
                original_content=original,
                patched_content=change.get("new_content", ""),
                diff_text=change.get("explanation", ""),
            )
            db.add(patch)
        db.commit()

        # Terminal'de göster
        print("\n" + "═" * 60)
        print("🤖 AI TARAFINDAN ÖNERİLEN KOD DEĞİŞİKLİĞİ")
        print("═" * 60)
        print(f"  Repo  : {repo.owner}/{repo.name}")
        print(f"  Issue : #{issue.issue_number} - {issue.title}")
        print(f"  Zorluk: {difficulty}/10")
        print(f"  Branch: {branch_name}")
        print(f"  Commit: {commit_msg}")
        if sandbox_passed is not None:
            emoji = "✅" if sandbox_passed else "❌"
            print(f"  Test  : {emoji} Docker sandbox")
        print("─" * 60)
        for change in changes:
            print(f"  📄 {change['file_path']}")
            print(f"     {change.get('explanation', 'N/A')}")
        print("─" * 60)
        print(f"  👉 Onay: http://127.0.0.1:8000/docs")
        print(f"     Aksiyon ID: {action.id}")
        print("═" * 60 + "\n")

        logger.warning(f"  ⏳ ONAY BEKLİYOR: Aksiyon #{action.id}")

    # ══════════════════════════════════════════════════════════
    #  PHASE 6: ONAY SONRASI İŞLEMLER
    # ══════════════════════════════════════════════════════════

    async def process_approved_action(self, action_id: int):
        """Onaylanmış bir ISSUE_SOLVING aksiyonunu PR'a dönüştürür."""
        db = SessionLocal()
        try:
            action = db.query(AgentActionHistory).filter(
                AgentActionHistory.id == action_id
            ).first()
            if not action or action.status != "APPROVED":
                return

            repo = db.query(Repo).filter(Repo.id == action.repo_id).first()
            if not repo:
                return

            issue = db.query(Issue).filter(
                Issue.id == action.issue_id
            ).first() if action.issue_id else None

            patches = db.query(CodePatch).filter(
                CodePatch.action_id == action.id
            ).all()

            action.status = "IN_PROGRESS"
            db.commit()

            logger.info(f"🚀 PR pipeline başlatılıyor: {repo.owner}/{repo.name}")

            # 0. Kullanıcı bilgisi
            user_login = await self.github.get_authenticated_user()
            if not user_login:
                logger.error("❌ GitHub token geçersiz!")
                action.status = "FAILED"
                db.commit()
                return

            # 1. Fork
            logger.info(f"  1/5 Fork ediliyor...")
            fork = await self.github.fork_repository(repo.owner, repo.name)
            if not fork:
                action.status = "FAILED"
                db.commit()
                return
            await asyncio.sleep(5)  # Fork'un hazır olmasını bekle

            # 2. Default branch SHA
            logger.info(f"  2/5 Base SHA alınıyor...")
            default_branch = await self.github.get_repo_default_branch(
                user_login, repo.name
            ) or repo.default_branch or "main"

            base_sha = await self.github.get_repo_base_sha(
                user_login, repo.name, default_branch
            )
            if not base_sha:
                logger.error("❌ Base SHA alınamadı. Fork henüz hazır olmayabilir.")
                action.status = "FAILED"
                db.commit()
                return

            # 3. Branch oluştur
            logger.info(f"  3/5 Branch oluşturuluyor: {action.proposed_branch}")
            await self.github.create_branch(
                user_login, repo.name, action.proposed_branch, base_sha
            )

            # 4. Dosyaları commit et
            logger.info(f"  4/5 {len(patches)} dosya commit ediliyor...")
            for patch in patches:
                success = await self.github.update_file(
                    owner=user_login,
                    name=repo.name,
                    path=patch.file_path,
                    content=patch.patched_content,
                    message=action.commit_message,
                    branch=action.proposed_branch,
                )
                if not success:
                    logger.error(f"❌ Dosya commit edilemedi: {patch.file_path}")
                    action.status = "FAILED"
                    db.commit()
                    return

            # 5. PR açıklaması üret ve PR aç
            logger.info(f"  5/5 PR açılıyor...")
            pr_body = await self.ai.generate_pr_description(
                issue_title=issue.title if issue else "Code improvement",
                issue_url=issue.url if issue else "",
                changes_summary=action.details.get("changes_summary", ""),
                files_changed=action.details.get("files_changed", []),
            ) or f"Automated fix for issue #{issue.issue_number if issue else 'N/A'}"

            pr_url = await self.github.create_pull_request(
                original_owner=repo.owner,
                name=repo.name,
                title=action.commit_message,
                body=pr_body,
                head_branch=action.proposed_branch,
                base_branch=default_branch,
            )

            if pr_url:
                action.status = "SUCCESS"
                action.pr_url = pr_url
                action.completed_at = datetime.now(timezone.utc)
                db.commit()
                self.stats["prs_created"] += 1
                logger.success(f"  ✅ PR oluşturuldu: {pr_url}")
            else:
                action.status = "FAILED"
                db.commit()
                logger.error("❌ PR açılamadı!")

        except Exception as e:
            logger.error(f"PR pipeline hatası: {e}")
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()

    async def process_approved_comment(self, comment_id: int):
        """Onaylanmış bir yorumu GitHub'a gönderir."""
        db = SessionLocal()
        try:
            comment = db.query(AgentComment).filter(
                AgentComment.id == comment_id
            ).first()
            if not comment or comment.status != "APPROVED":
                return

            repo = db.query(Repo).filter(Repo.id == comment.repo_id).first()
            if not repo:
                return

            posted_url = None

            if comment.target_type == "ISSUE":
                posted_url = await self.github.post_issue_comment(
                    owner=repo.owner,
                    name=repo.name,
                    issue_number=comment.target_number,
                    body=comment.body,
                )
            elif comment.target_type == "DISCUSSION":
                if comment.target_node_id:
                    posted_url = await self.github.post_discussion_comment(
                        discussion_node_id=comment.target_node_id,
                        body=comment.body,
                    )

            if posted_url:
                comment.status = "POSTED"
                comment.posted_url = posted_url
                comment.posted_at = datetime.now(timezone.utc)
                db.commit()
                logger.success(f"  ✅ Yorum gönderildi: {posted_url}")
            else:
                comment.status = "FAILED"
                db.commit()
                logger.error(f"  ❌ Yorum gönderilemedi: {comment.target_type} #{comment.target_number}")

        except Exception as e:
            logger.error(f"Yorum gönderme hatası: {e}")
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()
