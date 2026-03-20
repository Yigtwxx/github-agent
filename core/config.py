"""
GitHub AI Agent - Merkezi Konfigürasyon
Tüm ayarlar .env dosyasından veya ortam değişkenlerinden okunur.
"""
import os
from pydantic_settings import BaseSettings
from pydantic import validator
from typing import List


class Settings(BaseSettings):
    PROJECT_NAME: str = "GitHub AI Agent"

    # ── PostgreSQL ─────────────────────────────────────────────
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "github-agents"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── GitHub ─────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_MAX_REQUESTS_PER_HOUR: int = 4500   # GitHub limit = 5000, güvenli marj
    GITHUB_RETRY_MAX_ATTEMPTS: int = 3
    GITHUB_RETRY_BASE_DELAY: float = 1.0       # saniye (exponential: 1 → 2 → 4)

    @validator("GITHUB_TOKEN")
    def github_token_must_be_set(cls, v):
        if not v:
            raise ValueError(
                "GITHUB_TOKEN zorunludur. .env dosyasına ekleyin. "
                "Token almak için: https://github.com/settings/tokens"
            )
        return v

    # ── Hedef Diller (ağırlıklı Python) ────────────────────────
    TARGET_LANGUAGES: List[str] = [
        "Python", "JavaScript", "TypeScript", "Go", "Rust"
    ]
    PRIMARY_LANGUAGE: str = "Python"

    # ── Trend Avcısı ───────────────────────────────────────────
    TRENDING_DAYS_AGO: int = 7
    TRENDING_LIMIT_PER_LANGUAGE: int = 5
    MIN_STARS_THRESHOLD: int = 50

    # ── Issue / Discussion Limitleri ───────────────────────────
    ISSUES_PER_REPO: int = 10
    DISCUSSIONS_PER_REPO: int = 5
    ISSUE_TARGET_LABELS: List[str] = [
        "good first issue", "help wanted", "bug",
        "enhancement", "documentation"
    ]

    # ── Ollama / AI ────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:7b"
    OLLAMA_TEMPERATURE: float = 0.3
    OLLAMA_NUM_PREDICT: int = 4096
    OLLAMA_RETRY_MAX_ATTEMPTS: int = 3
    OLLAMA_RETRY_BASE_DELAY: float = 2.0       # saniye (exponential: 2 → 4 → 8)

    # ── ChromaDB ───────────────────────────────────────────────
    CHROMA_PERSIST_DIRECTORY: str = os.path.join(os.getcwd(), "chroma_db")

    # ── Çalışma Alanı ─────────────────────────────────────────
    WORKSPACE_DIR: str = os.path.join(os.getcwd(), "workspace")

    # ── Döngü Zamanlaması ──────────────────────────────────────
    LOOP_INTERVAL_SECONDS: int = 3600          # ana döngü arası (1 saat)
    ERROR_RETRY_DELAY_SECONDS: int = 60        # hata sonrası bekleme
    TASK_CONCURRENCY: int = 3                  # paralel repo işleme

    # ── İnsan Onayı ───────────────────────────────────────────
    REQUIRE_APPROVAL_FOR_PR: bool = True
    REQUIRE_APPROVAL_FOR_COMMENT: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Workspace dizinini oluştur
os.makedirs(settings.WORKSPACE_DIR, exist_ok=True)
