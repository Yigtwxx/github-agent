"""
Veritabanı tablolarını oluşturur / günceller.
İlk kurulumda veya şema değişikliğinde çalıştırın.
"""
from loguru import logger


def init_db():
    logger.info("Veritabanı tabloları oluşturuluyor...")
    try:
        from database.session import engine, Base
        # Tüm modelleri import et (tabloların Base'e kaydolması için)
        from database.models import (  # noqa: F401
            Repo, Issue, Discussion,
            AgentComment, CodePatch, AgentActionHistory,
        )
        Base.metadata.create_all(bind=engine)
        logger.success("Veritabanı tabloları başarıyla oluşturuldu / güncellendi.")
    except Exception as e:
        logger.error(f"Veritabanı kurulumu hatası: {e}")
        raise


if __name__ == "__main__":
    init_db()
