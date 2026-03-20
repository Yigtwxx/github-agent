"""
Ollama AI Client - Async, çok yönlü AI muhakeme motoru.

5 uzman prompt stratejisi:
  1. analyze_issue_for_support  → Topluluk desteği cevabı
  2. analyze_issue_solvability  → Issue zorluk & çözülebilirlik skoru
  3. generate_code_fix          → Gerçek kod patch üretimi
  4. generate_pr_description    → Profesyonel PR açıklaması
  5. generate_discussion_reply  → Discussion cevabı

Tüm çağrılar async, yapılandırılmış JSON çıktı destekli.
"""
import json
from typing import Optional

import ollama
from loguru import logger

from core.config import settings


class OllamaAIClient:
    def __init__(self):
        self.host = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.client = ollama.AsyncClient(host=self.host)
        logger.info(f"Ollama AI Client başlatıldı (Model: {self.model}, Host: {self.host})")

    async def _generate(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> Optional[str]:
        """
        Temel üretim fonksiyonu. Başarısız olursa exponential backoff ile yeniden dener.
        json_mode=True ise modelden JSON çıktı beklenir.
        """
        import asyncio
        options = {
            "temperature": settings.OLLAMA_TEMPERATURE,
            "num_predict": settings.OLLAMA_NUM_PREDICT,
        }
        last_exc: Exception = None
        for attempt in range(1, settings.OLLAMA_RETRY_MAX_ATTEMPTS + 1):
            try:
                response = await self.client.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    options=options,
                    format="json" if json_mode else "",
                )
                return response["message"]["content"]
            except Exception as e:
                last_exc = e
                delay = settings.OLLAMA_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Ollama API hatası (deneme {attempt}/{settings.OLLAMA_RETRY_MAX_ATTEMPTS}): {e}. "
                    f"{delay}s sonra tekrar deneniyor..."
                )
                if attempt < settings.OLLAMA_RETRY_MAX_ATTEMPTS:
                    await asyncio.sleep(delay)
        logger.error(f"Ollama {settings.OLLAMA_RETRY_MAX_ATTEMPTS} denemede yanıt vermedi: {last_exc}")
        return None

    async def _generate_json(self, system_prompt: str, user_prompt: str) -> Optional[dict]:
        """JSON modda üret ve parse et."""
        raw = await self._generate(system_prompt, user_prompt, json_mode=True)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"JSON parse hatası, None döndürülüyor. Ham yanıt: {raw[:200]}...")
            return None

    # ══════════════════════════════════════════════════════════
    #  1. TOPLULUK DESTEĞİ - Issue'ya cevap yaz
    # ══════════════════════════════════════════════════════════

    async def analyze_issue_for_support(
        self, issue_title: str, issue_body: str, repo_context: str = ""
    ) -> dict:
        system_prompt = """Sen uzman bir açık kaynak yazılım geliştiricisi ve GitHub Community Support ajanısın.
Görevin: Kullanıcıların açtığı Issue veya Discussion'ları okuyup, amaca yönelik, nazik ve teknik olarak doğru çözümler üretmek.

Kurallar:
1. Sorun anlaşılıyorsa, çözüm yollarını maddeler halinde sırala.
2. Sorun eksik bilgi içeriyorsa (log yok, versiyon yok vb.), kibarca eksik bilgileri iste.
3. Yanıtını GitHub Flavored Markdown formatıyla ver.
4. Yanıt profesyonel, detaylı ve yardımsever olmalı.
5. Eğer kod örneği veriyorsan, dil etiketli kod bloğu kullan.
6. Asla "Ben bir AI'yım" deme. Deneyimli bir geliştirici gibi yaz.
7. İngilizce yaz (GitHub'da uluslararası kitle var)."""

        context_section = f"\n\nRAG Context (repo docs/code):\n{repo_context}" if repo_context else ""

        user_prompt = f"""Please analyze this GitHub Issue and write a professional, helpful response.

**Issue Title:** {issue_title}

**Issue Body:**
{issue_body}
{context_section}"""

        logger.debug(f"AI: Issue desteği üretiliyor → {issue_title}")
        reply = await self._generate(system_prompt, user_prompt)

        if reply:
            return {"status": "success", "reply": reply}
        return {"status": "error", "reply": "AI yanıt üretemedi."}

    # ══════════════════════════════════════════════════════════
    #  2. ISSUE ÇÖZÜLEBİLİRLİK ANALİZİ
    # ══════════════════════════════════════════════════════════

    async def analyze_issue_solvability(
        self,
        issue_title: str,
        issue_body: str,
        labels: list[str] = None,
        repo_context: str = "",
    ) -> Optional[dict]:
        """
        Issue'nun AI tarafından çözülebilir olup olmadığını analiz eder.
        Returns: {
            "solvability": "SOLVABLE|NEEDS_INFO|TOO_COMPLEX|SKIP",
            "difficulty": 1-10,
            "reasoning": "...",
            "suggested_approach": "...",
            "estimated_files": ["file1.py", "file2.py"]
        }
        """
        system_prompt = """You are a senior software engineer evaluating GitHub issues.
Analyze the issue and determine if an AI agent could realistically solve it.

Return a JSON object with EXACTLY these fields:
{
  "solvability": "SOLVABLE" or "NEEDS_INFO" or "TOO_COMPLEX" or "SKIP",
  "difficulty": integer from 1 to 10,
  "reasoning": "Brief explanation of your assessment",
  "suggested_approach": "How to fix this issue step by step",
  "estimated_files": ["list", "of", "likely", "files", "to", "modify"]
}

Guidelines:
- SOLVABLE: Clear bug fix, documentation fix, typo, simple feature, test addition
- NEEDS_INFO: Missing reproduction steps, logs, or version info
- TOO_COMPLEX: Major refactor, breaking changes, security-critical
- SKIP: Feature requests without clear scope, meta-discussions
- difficulty 1-3: typos, docs, config changes
- difficulty 4-6: simple bug fixes, small features
- difficulty 7-10: complex logic, multi-file changes"""

        labels_str = ", ".join(labels) if labels else "none"
        context_section = f"\n\nRepository Context:\n{repo_context}" if repo_context else ""

        user_prompt = f"""Analyze this issue:

**Title:** {issue_title}
**Labels:** {labels_str}
**Body:**
{issue_body}
{context_section}"""

        logger.debug(f"AI: Çözülebilirlik analizi → {issue_title}")
        return await self._generate_json(system_prompt, user_prompt)

    # ══════════════════════════════════════════════════════════
    #  3. KOD PATCH ÜRETİMİ
    # ══════════════════════════════════════════════════════════

    async def generate_code_fix(
        self,
        issue_title: str,
        issue_body: str,
        file_contents: dict[str, str],
        suggested_approach: str = "",
    ) -> Optional[dict]:
        """
        Issue'ya çözüm olarak gerçek kod değişikliği üretir.

        Args:
            file_contents: {"src/utils.py": "file content...", ...}

        Returns: {
            "changes": [
                {"file_path": "src/utils.py", "new_content": "...", "explanation": "..."},
                ...
            ],
            "commit_message": "Fix: ...",
            "summary": "..."
        }
        """
        system_prompt = """You are an expert programmer tasked with fixing a GitHub issue.
You will receive the issue details and relevant source file contents.
Generate the EXACT code changes needed.

Return a JSON object:
{
  "changes": [
    {
      "file_path": "exact/path/to/file.py",
      "new_content": "COMPLETE new file content with the fix applied",
      "explanation": "What was changed and why"
    }
  ],
  "commit_message": "A conventional commit message (e.g., 'fix: resolve null pointer in parser')",
  "summary": "Brief summary of all changes"
}

Rules:
1. Return the COMPLETE file content, not just the diff.
2. Make minimal, focused changes. Don't refactor unrelated code.
3. Keep the existing code style.
4. If you need to add imports, add them in the correct position.
5. If you're unsure, err on the side of doing less.
6. The commit message must follow conventional commits format."""

        files_section = ""
        for path, content in file_contents.items():
            truncated = content[:8000] if len(content) > 8000 else content
            files_section += f"\n--- {path} ---\n```\n{truncated}\n```\n"

        user_prompt = f"""Fix this issue:

**Issue:** {issue_title}
**Details:** {issue_body}

**Suggested Approach:** {suggested_approach}

**Relevant Source Files:**
{files_section}"""

        logger.debug(f"AI: Kod patch üretiliyor → {issue_title}")
        return await self._generate_json(system_prompt, user_prompt)

    # ══════════════════════════════════════════════════════════
    #  4. PR AÇIKLAMASI ÜRETİMİ
    # ══════════════════════════════════════════════════════════

    async def generate_pr_description(
        self,
        issue_title: str,
        issue_url: str,
        changes_summary: str,
        files_changed: list[str],
    ) -> Optional[str]:
        """Profesyonel bir PR açıklaması üretir."""
        system_prompt = """You are writing a professional Pull Request description for GitHub.
Write in English. Use GitHub Flavored Markdown.
Include: what was changed, why, and how to test it.
Be concise but thorough. Do NOT say you are an AI."""

        user_prompt = f"""Write a PR description for:

**Related Issue:** {issue_title} ({issue_url})

**Changes Summary:** {changes_summary}

**Files Changed:** {', '.join(files_changed)}

Format:
## What
Brief description of changes

## Why
Link to the issue and explanation

## Changes
- Bullet points of specific changes

## Testing
How to verify the changes work"""

        return await self._generate(system_prompt, user_prompt)

    # ══════════════════════════════════════════════════════════
    #  5. DISCUSSION CEVABI
    # ══════════════════════════════════════════════════════════

    async def generate_discussion_reply(
        self,
        discussion_title: str,
        discussion_body: str,
        category: str = "",
        repo_context: str = "",
    ) -> dict:
        """Discussion'a yardımcı bir cevap üretir."""
        system_prompt = """You are a helpful open-source community member answering a GitHub Discussion.
Be friendly, professional, and technically accurate.
Write in English using GitHub Flavored Markdown.
If the question is about code, include code examples.
If it's a feature request, provide constructive feedback.
If it's a Q&A, provide a clear answer.
Do NOT mention that you are an AI."""

        category_note = f"\n**Category:** {category}" if category else ""
        context_section = f"\n\nRAG Context:\n{repo_context}" if repo_context else ""

        user_prompt = f"""Please respond to this GitHub Discussion:

**Title:** {discussion_title}{category_note}

**Body:**
{discussion_body}
{context_section}"""

        logger.debug(f"AI: Discussion cevabı üretiliyor → {discussion_title}")
        reply = await self._generate(system_prompt, user_prompt)

        if reply:
            return {"status": "success", "reply": reply}
        return {"status": "error", "reply": "AI yanıt üretemedi."}
