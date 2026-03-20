"""
GitHub AI Agent - Ana başlatma dosyası.
Veritabanı kontrol → Tablolar oluştur → FastAPI + Otonom döngü başlat.
"""
import os
import sys

import uvicorn
from loguru import logger

from core.config import settings


def check_prerequisites():
    """Başlatma öncesi ön koşul kontrolü."""
    errors = []

    if not settings.GITHUB_TOKEN:
        errors.append("❌ GITHUB_TOKEN ayarlanmamış! .env dosyasını kontrol edin.")

    if not os.path.exists(".env"):
        errors.append("❌ .env dosyası bulunamadı! .env.example dosyasını kopyalayın.")

    if errors:
        for err in errors:
            logger.error(err)
        sys.exit(1)


def start_agent_server():
    """FastAPI sunucusunu ve otonom agent döngüsünü başlatır."""
    check_prerequisites()

    print(f"""
╔══════════════════════════════════════════════════╗
║        🤖 {settings.PROJECT_NAME:<30}       ║
╠══════════════════════════════════════════════════╣
║  📡 API Docs  : http://localhost:8000/docs       ║
║  ❤️  Health    : http://localhost:8000/health     ║
║  🧠 AI Model  : {settings.OLLAMA_MODEL:<24}     ║
║  📋 Diller    : {', '.join(settings.TARGET_LANGUAGES):<24}     ║
║  ⏰ Döngü     : {settings.LOOP_INTERVAL_SECONDS}s{' ' * 27}║
╚══════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    start_agent_server()
