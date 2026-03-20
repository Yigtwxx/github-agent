"""
Veritabanı modelleri - Genişletilmiş şema.
Repo, Issue, Discussion, AgentComment, CodePatch, AgentActionHistory.
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    Boolean, JSON, UniqueConstraint, Float
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from database.session import Base


# ──────────────────────────────────────────────────────────────
# REPO
# ──────────────────────────────────────────────────────────────
class Repo(Base):
    __tablename__ = "repos"

    id = Column(Integer, primary_key=True, index=True)
    owner = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    url = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    stars = Column(Integer, default=0)
    language = Column(String, nullable=True)
    default_branch = Column(String, default="main")
    topics = Column(JSON, nullable=True)              # ["machine-learning", "cli", ...]
    open_issue_count = Column(Integer, default=0)
    has_good_first_issues = Column(Boolean, default=False)

    is_trending = Column(Boolean, default=False)
    is_forked = Column(Boolean, default=False)
    cloned_path = Column(String, nullable=True)        # lokal klon dizini
    rag_indexed = Column(Boolean, default=False)       # RAG'a indekslenmiş mi?
    last_checked_at = Column(DateTime, nullable=True)

    # Skor: repo ne kadar değerli bir hedef? (0-100)
    priority_score = Column(Float, default=0.0)

    discovered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    issues = relationship("Issue", back_populates="repo", cascade="all, delete-orphan")
    discussions = relationship("Discussion", back_populates="repo", cascade="all, delete-orphan")
    actions = relationship("AgentActionHistory", back_populates="repo", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("owner", "name", name="uq_repo_owner_name"),
    )


# ──────────────────────────────────────────────────────────────
# ISSUE
# ──────────────────────────────────────────────────────────────
class Issue(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)
    issue_number = Column(Integer, nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    state = Column(String, default="OPEN")             # OPEN, CLOSED
    url = Column(String, nullable=True)
    labels = Column(JSON, nullable=True)               # ["bug", "help wanted", ...]
    comment_count = Column(Integer, default=0)
    is_good_first_issue = Column(Boolean, default=False)

    # AI tarafından atanan zorluk skoru (1-10)
    ai_difficulty_score = Column(Float, nullable=True)
    ai_solvability = Column(String, nullable=True)     # SOLVABLE, NEEDS_INFO, TOO_COMPLEX, SKIP

    created_at = Column(DateTime, nullable=True)
    analyzed_at = Column(DateTime, nullable=True)

    repo = relationship("Repo", back_populates="issues")

    __table_args__ = (
        UniqueConstraint("repo_id", "issue_number", name="uq_issue_repo_number"),
    )


# ──────────────────────────────────────────────────────────────
# DISCUSSION
# ──────────────────────────────────────────────────────────────
class Discussion(Base):
    __tablename__ = "discussions"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)
    discussion_number = Column(Integer, nullable=False, index=True)
    node_id = Column(String, nullable=True)            # GraphQL node ID (yorum göndermek için)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=True)
    category = Column(String, nullable=True)           # Q&A, General, Ideas, ...
    url = Column(String, nullable=True)
    answer_count = Column(Integer, default=0)
    is_answered = Column(Boolean, default=False)

    created_at = Column(DateTime, nullable=True)
    analyzed_at = Column(DateTime, nullable=True)

    repo = relationship("Repo", back_populates="discussions")

    __table_args__ = (
        UniqueConstraint("repo_id", "discussion_number", name="uq_disc_repo_number"),
    )


# ──────────────────────────────────────────────────────────────
# AGENT COMMENT  (Issue veya Discussion'a gönderilen/bekleyen yorumlar)
# ──────────────────────────────────────────────────────────────
class AgentComment(Base):
    __tablename__ = "agent_comments"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=False)

    # Hangi hedefe gidiyor?
    target_type = Column(String, nullable=False)       # ISSUE veya DISCUSSION
    target_number = Column(Integer, nullable=False)    # issue / discussion numarası
    target_node_id = Column(String, nullable=True)     # GraphQL node ID (discussion comment için)
    target_url = Column(String, nullable=True)

    # AI tarafından üretilen yorum içeriği
    body = Column(Text, nullable=False)

    # Durum
    status = Column(String, default="AWAITING_APPROVAL")  # AWAITING_APPROVAL, APPROVED, REJECTED, POSTED, FAILED

    posted_url = Column(String, nullable=True)         # Gönderildiğinde yorum URL'si

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    posted_at = Column(DateTime, nullable=True)

    repo = relationship("Repo")


# ──────────────────────────────────────────────────────────────
# CODE PATCH  (Gerçek dosya bazlı kod değişiklikleri)
# ──────────────────────────────────────────────────────────────
class CodePatch(Base):
    __tablename__ = "code_patches"

    id = Column(Integer, primary_key=True, index=True)
    action_id = Column(Integer, ForeignKey("agent_action_history.id"), nullable=False)

    file_path = Column(String, nullable=False)         # e.g. "src/utils.py"
    original_content = Column(Text, nullable=True)     # orijinal dosya içeriği
    patched_content = Column(Text, nullable=False)     # yamalı dosya içeriği
    diff_text = Column(Text, nullable=True)            # unified diff

    action = relationship("AgentActionHistory", back_populates="patches")


# ──────────────────────────────────────────────────────────────
# AGENT ACTION HISTORY
# ──────────────────────────────────────────────────────────────
class AgentActionHistory(Base):
    __tablename__ = "agent_action_history"

    id = Column(Integer, primary_key=True, index=True)
    repo_id = Column(Integer, ForeignKey("repos.id"), nullable=True)

    # TREND_HUNT, COMMUNITY_SUPPORT, ISSUE_SOLVING, PR_CREATION, DISCUSSION_REPLY
    action_type = Column(String, nullable=False, index=True)

    # PENDING, SUCCESS, FAILED, AWAITING_APPROVAL, APPROVED, REJECTED, IN_PROGRESS
    status = Column(String, default="PENDING")
    details = Column(JSON, nullable=True)

    # PR bilgileri
    proposed_branch = Column(String, nullable=True)
    commit_message = Column(Text, nullable=True)
    pr_url = Column(String, nullable=True)

    # İlişkili issue
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=True)

    # Docker sandbox test sonucu
    sandbox_test_passed = Column(Boolean, nullable=True)
    sandbox_test_logs = Column(Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    repo = relationship("Repo", back_populates="actions")
    issue = relationship("Issue")
    patches = relationship("CodePatch", back_populates="action", cascade="all, delete-orphan")
