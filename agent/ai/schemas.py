"""Pydantic schemas for structured LLM outputs.

Every JSON-producing capability validates against one of these models instead
of trusting raw ``json.loads``. This bounds the blast radius of prompt
injection: an attacker who smuggles "output X" into an issue body still has to
satisfy the schema, and arbitrary instructions cannot change the contract.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Solvability = Literal["SOLVABLE", "NEEDS_INFO", "TOO_COMPLEX", "SKIP"]


class SolvabilityResult(BaseModel):
    """Assessment of whether an AI agent could solve an issue."""

    solvability: Solvability = "SKIP"
    difficulty: int = Field(default=10, ge=1, le=10)
    impact: int = Field(default=5, ge=1, le=10)
    reasoning: str = ""
    suggested_approach: str = ""
    estimated_files: list[str] = Field(default_factory=list)


class CodeChange(BaseModel):
    """A single full-file replacement."""

    file_path: str
    new_content: str
    explanation: str = ""


class CodePatchResult(BaseModel):
    """A set of code changes that resolve an issue."""

    changes: list[CodeChange] = Field(default_factory=list)
    commit_message: str = ""
    summary: str = ""


class CritiqueResult(BaseModel):
    """Self-critique of a drafted community answer."""

    needs_revision: bool = False
    issues: list[str] = Field(default_factory=list)
    suggestions: str = ""


class RepoSummary(BaseModel):
    """Concise repository overview used to ground downstream prompts."""

    purpose: str = ""
    key_modules: list[str] = Field(default_factory=list)
    setup_notes: str = ""
    contribution_hotspots: list[str] = Field(default_factory=list)
