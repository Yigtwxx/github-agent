# 🤖 GitHub Autonomous AI Agent

Bu proje, GitHub uzerindeki popüler repoları otomatik olarak bulan, topluluk sorularını (Issue/Discussion) analiz edip cevaplayan ve otonom PR'lar açan bir yapay zeka ajanıdır.

## 🚀 Hızlı Başlangıç

### 1. Ön Gereksinimler
- **Python 3.10+**
- **Docker** (İzole testler için)
- **PostgreSQL** (Veri depolama için)
- **Ollama** (Qwen 2.5 modeli yüklü olmalı: `ollama run qwen2.5`)

### 2. Kurulum
```bash
# Proje dizinine gidin
cd github-agent

# Sanal ortam oluşturun ve aktif edin
python -m venv venv
.\venv\Scripts\Activate.ps1

# Bağımlılıkları kurun
pip install -r requirements.txt
```

### 3. Yapılandırma
`.env.example` dosyasını `.env` olarak kopyalayın ve içine **GitHub Token** ve **Postgres** bilgilerinizi girin.

### 4. Çalıştırma
```bash
# Veritabanı tablolarını oluşturun
python init_db.py

# Ajanı başlatın
python run.py
```

## 🛠 Mimari Bileşenler
- **FastAPI:** Ajanın orkestratör kontrol paneli.
- **GitHub GraphQL:** Veri çekme ve etkileşim.
- **Ollama (Qwen 2.5):** Yerel AI muhakemesi.
- **ChromaDB:** RAG tabanlı kod anlama.
- **Docker:** Güvenli kod yürütme ortamı.

---
*Hazırlayan: Antigravity AI*
