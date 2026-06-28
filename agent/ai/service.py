"""High-level AI reasoning service.

Combines a swappable :class:`LLMProvider` with externalized prompts, untrusted
input fencing, token budgeting, and schema-validated structured outputs.

Method names and return shapes are stable so the orchestrator can swap the
underlying provider with a one-line change, while new capabilities
(critique/refine, repo summary) build on the same primitives.
"""
from __future__ import annotations

import json
from typing import Type, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError

from agent.ai import sanitize
from agent.ai.schemas import (
    CodePatchResult,
    CritiqueResult,
    RepoSummary,
    SolvabilityResult,
)
from agent.prompts import render
from agent.providers.base import ChatMessage, LLMError, LLMProvider
from agent.providers.tokens import count_tokens, trim_to_budget
from core.config import settings

T = TypeVar("T", bound=BaseModel)

# Tokens reserved as a safety margin between input + output and the context window.
_BUDGET_MARGIN = 512


class AIReasoningService:
    """Capability-oriented wrapper over an LLM provider."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    # ── Core primitives ────────────────────────────────────────

    async def _chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str | None:
        """Run one chat turn, trimming the user prompt to fit the context window."""
        available = (
            self.provider.context_window
            - max_tokens
            - count_tokens(system)
            - _BUDGET_MARGIN
        )
        if available <= 0:
            logger.error("Token budget exhausted by system prompt + output reservation.")
            return None
        if count_tokens(user) > available:
            logger.warning("Trimming user prompt to fit token budget ({} tokens).", available)
            user = trim_to_budget(user, available)

        messages = [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ]
        try:
            result = await self.provider.chat(
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
            )
        except LLMError as exc:
            logger.error("LLM call failed: {}", exc)
            return None
        return result.text

    async def _chat_validated(
        self,
        name: str,
        model_cls: Type[T],
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **context,
    ) -> T | None:
        """Render a JSON-producing template, validate, and repair once on failure."""
        max_tokens = max_tokens or settings.LLM_MAX_OUTPUT_TOKENS
        system, user = render(name, **context)

        raw = await self._chat(
            system, user, temperature=temperature, max_tokens=max_tokens, json_mode=True
        )
        parsed = self._validate(raw, model_cls)
        if parsed is not None:
            return parsed

        # One bounded repair attempt: tell the model exactly what to return.
        logger.warning("Schema validation failed for '{}', attempting one repair.", name)
        repair_system = (
            system
            + "\n\nYour previous response was not valid JSON for the required schema. "
            "Return ONLY a single valid JSON object with the exact fields described."
        )
        raw = await self._chat(
            repair_system, user, temperature=0.0, max_tokens=max_tokens, json_mode=True
        )
        return self._validate(raw, model_cls)

    @staticmethod
    def _validate(raw: str | None, model_cls: Type[T]) -> T | None:
        if not raw:
            return None
        payload = _extract_json(raw)
        if payload is None:
            return None
        try:
            return model_cls.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Pydantic validation error for {}: {}", model_cls.__name__, exc)
            return None

    # ── 1. Community support: issue ─────────────────────────────

    async def analyze_issue_for_support(
        self, issue_title: str, issue_body: str, repo_context: str = ""
    ) -> dict:
        """Draft -> self-critique -> refine an issue reply. Returns {status, reply}."""
        reply = await self._draft_and_refine(
            draft_template="issue_support",
            title=issue_title,
            body=issue_body,
            repo_context=repo_context,
        )
        if reply:
            return {"status": "success", "reply": reply}
        return {"status": "error", "reply": "AI yanıt üretemedi."}

    # ── 5. Community support: discussion ────────────────────────

    async def generate_discussion_reply(
        self,
        discussion_title: str,
        discussion_body: str,
        category: str = "",
        repo_context: str = "",
    ) -> dict:
        reply = await self._draft_and_refine(
            draft_template="discussion_reply",
            title=discussion_title,
            body=discussion_body,
            repo_context=repo_context,
            category=category,
        )
        if reply:
            return {"status": "success", "reply": reply}
        return {"status": "error", "reply": "AI yanıt üretemedi."}

    async def _draft_and_refine(
        self,
        *,
        draft_template: str,
        title: str,
        body: str,
        repo_context: str,
        category: str = "",
    ) -> str | None:
        """Shared draft -> critique -> refine loop for community answers."""
        s = sanitize.make_sentinel()
        fenced_title = sanitize.fence(title, s)
        fenced_body = sanitize.fence(body, s)
        fenced_context = sanitize.fence(repo_context, s) if repo_context else ""

        system, user = render(
            draft_template,
            fenced_title=fenced_title,
            fenced_body=fenced_body,
            fenced_context=fenced_context,
            category=category,
        )
        draft = await self._chat(
            system,
            user,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        )
        if not draft:
            return None

        # Self-critique against the original question + context.
        fenced_question = sanitize.fence(f"{title}\n\n{body}", s)
        fenced_answer = sanitize.fence(draft, s)
        critique = await self._chat_validated(
            "critique",
            CritiqueResult,
            fenced_question=fenced_question,
            fenced_context=fenced_context,
            fenced_answer=fenced_answer,
        )
        if critique is None or not critique.needs_revision:
            return draft

        # Refine using the critique.
        r_system, r_user = render(
            "refine",
            fenced_question=fenced_question,
            fenced_answer=fenced_answer,
            issues="; ".join(critique.issues) or "none",
            suggestions=critique.suggestions or "Improve clarity and correctness.",
        )
        refined = await self._chat(
            r_system,
            r_user,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        )
        return refined or draft

    # ── 2. Solvability analysis ─────────────────────────────────

    async def analyze_issue_solvability(
        self,
        issue_title: str,
        issue_body: str,
        labels: list[str] | None = None,
        repo_context: str = "",
    ) -> dict | None:
        s = sanitize.make_sentinel()
        result = await self._chat_validated(
            "solvability",
            SolvabilityResult,
            fenced_title=sanitize.fence(issue_title, s),
            fenced_body=sanitize.fence(issue_body, s),
            fenced_context=sanitize.fence(repo_context, s) if repo_context else "",
            labels_str=", ".join(labels) if labels else "none",
        )
        return result.model_dump() if result else None

    # ── 3. Code fix generation ──────────────────────────────────

    async def generate_code_fix(
        self,
        issue_title: str,
        issue_body: str,
        file_contents: dict[str, str],
        suggested_approach: str = "",
    ) -> dict | None:
        s = sanitize.make_sentinel()
        files_section = "".join(
            f"\n--- {path} ---\n```\n{content}\n```\n"
            for path, content in file_contents.items()
        )
        result = await self._chat_validated(
            "code_fix",
            CodePatchResult,
            temperature=0.1,
            fenced_title=sanitize.fence(issue_title, s),
            fenced_body=sanitize.fence(issue_body, s),
            fenced_files=sanitize.fence(files_section, s, max_chars=40_000),
            suggested_approach=sanitize.cap(suggested_approach, 4_000),
        )
        return result.model_dump() if result else None

    async def repair_code_fix(
        self,
        issue_title: str,
        issue_body: str,
        file_contents: dict[str, str],
        previous_changes: list[dict],
        failure_log: str,
        suggested_approach: str = "",
    ) -> dict | None:
        """Repair a previously generated fix using the verification failure log.

        Reuses the :class:`CodePatchResult` contract; the model is shown its own
        previous changes plus why they failed (lint error or sandbox output) and
        must return a corrected, complete patch set.
        """
        s = sanitize.make_sentinel()
        files_section = "".join(
            f"\n--- {path} ---\n```\n{content}\n```\n"
            for path, content in file_contents.items()
        )
        previous_section = "".join(
            f"\n--- {c.get('file_path', '')} ---\n```\n{c.get('new_content', '')}\n```\n"
            for c in previous_changes
        )
        result = await self._chat_validated(
            "code_repair",
            CodePatchResult,
            temperature=0.1,
            fenced_title=sanitize.fence(issue_title, s),
            fenced_body=sanitize.fence(issue_body, s),
            fenced_files=sanitize.fence(files_section, s, max_chars=40_000),
            fenced_previous_changes=sanitize.fence(previous_section, s, max_chars=40_000),
            fenced_failure_log=sanitize.fence(failure_log, s, max_chars=8_000),
            suggested_approach=sanitize.cap(suggested_approach, 4_000),
        )
        return result.model_dump() if result else None

    # ── 4. PR description ───────────────────────────────────────

    async def generate_pr_description(
        self,
        issue_title: str,
        issue_url: str,
        changes_summary: str,
        files_changed: list[str],
    ) -> str | None:
        s = sanitize.make_sentinel()
        system, user = render(
            "pr_description",
            fenced_title=sanitize.fence(issue_title, s),
            fenced_summary=sanitize.fence(changes_summary, s),
            issue_url=issue_url,
            files_changed=", ".join(files_changed),
        )
        return await self._chat(
            system,
            user,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        )

    # ── Repo summarization (used by RAG phase) ──────────────────

    async def summarize_repo(self, readme: str, file_tree: str) -> RepoSummary | None:
        # Template added in the RAG phase; method exposed here for reuse.
        s = sanitize.make_sentinel()
        return await self._chat_validated(
            "repo_summary",
            RepoSummary,
            fenced_readme=sanitize.fence(readme, s, max_chars=20_000),
            fenced_tree=sanitize.fence(file_tree, s, max_chars=8_000),
        )

    async def aclose(self) -> None:
        await self.provider.aclose()


def _extract_json(text: str) -> dict | None:
    """Parse a JSON object from model output, tolerating code fences/prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced-looking {...} span.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None
