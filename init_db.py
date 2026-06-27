"""
Veritabanı tablolarını oluşturur (bootstrap).

NOT: `create_all()` yalnızca EKSİK TABLOLARI oluşturur; mevcut tablolara yeni
SÜTUN EKLEMEZ. Şema değişiklikleri (sütun ekleme/çıkarma) artık Alembic ile
yönetilir:

  - Yeni / boş DB:    python init_db.py  &&  alembic stamp head
  - Mevcut DB güncelle:                     alembic upgrade head
  - Model değiştikten sonra:
        alembic revision --autogenerate -m "..."  &&  alembic upgrade head
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
            TrendSignal,
        )
        Base.metadata.create_all(bind=engine)
        logger.success("Veritabanı tabloları başarıyla oluşturuldu / güncellendi.")
    except Exception as e:
        logger.error(f"Veritabanı kurulumu hatası: {e}")
        raise


if __name__ == "__main__":
    init_db()
