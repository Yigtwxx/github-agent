#  GitHub Autonomous AI Agent v2.0

Popüler GitHub repolarını **otomatik keşfeden**, topluluk sorularına (Issue & Discussion) **AI cevapları üreten**, çözülebilir issue'lar için **gerçek kod yamaları oluşturup PR açan** otonom bir yapay zeka ajanı.

---

##  Özellikler

| Özellik | Açıklama |
|---|---|
| 🔍 **Trend Avcısı** | 5 dilde (Python, JS, TS, Go, Rust) popüler repoları keşfeder, öncelik skorlar |
| 💬 **Issue Desteği** | Issue'ları analiz eder, RAG bağlamıyla AI cevabı üretir |
| 🗣️ **Discussion Desteği** | GitHub Discussions'a otomatik cevap üretir |
| 🔧 **Issue Çözücü** | Çözülebilirlik analizi → Gerçek kod patch üretimi → Syntax check → Docker sandbox testi |
| 🚀 **Otonom PR** | Fork → Branch → Commit → PR pipeline'ı |
| 🛡️ **İnsan Onayı** | Tüm yorumlar ve PR'lar gönderilmeden önce onay bekler |
| 📚 **RAG Pipeline** | Repo klonla → ChromaDB'ye indeksle → Issue bağlamında akıllı kod arama |
| 🐳 **Docker Sandbox** | AI kodunu izole ortamda test eder |
| ⚡ **Rate Limiting** | GitHub API limitlerini otomatik yönetir |

---

## 🛠️ Mimari

```
┌─────────────────────────────────────────────┐
│              FastAPI (api/main.py)           │
│  /health  /stats  /pending  /approve  /...  │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│         Agent Orchestrator                   │
│  6 Phase Pipeline:                           │
│  Trend → Setup → Community → Discussion     │
│  → Issue Solve → PR Pipeline                │
└──┬───────┬───────┬───────┬──────────────────┘
   │       │       │       │
┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
│ Git │ │ AI  │ │ RAG │ │Docker│
│ Hub │ │Ollama│ │Chroma│ │Sand │
│Client│ │Client│ │ DB  │ │ box │
└─────┘ └─────┘ └─────┘ └─────┘
```

---

## 🚀 Hızlı Başlangıç

### Ön Gereksinimler
- **Python 3.10+**
- **PostgreSQL** (veri depolama)
- **Ollama** + `qwen3-coder:30b` modeli
- **Docker** (sandbox testleri için)
- **Git** (repo klonlama için)

### 1. Kurulum

```bash
# Sanal ortam
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
# source venv/bin/activate     # Linux/Mac

# Bağımlılıklar
pip install -r requirements.txt

# Ollama modeli (start.ps1 bunu otomatik indirir; elle de yapabilirsiniz)
ollama pull qwen3-coder:30b
```

### 2. Yapılandırma

```bash
copy .env.example .env    # Windows
# cp .env.example .env    # Linux/Mac
```

`.env` dosyasını düzenleyin:
- `GITHUB_TOKEN` → [GitHub PAT oluştur](https://github.com/settings/tokens) (gerekli yetkiler: `repo`, `read:discussion`, `write:discussion`)
- `POSTGRES_*` → PostgreSQL bağlantı bilgileri

### 3. Veritabanı

Şema değişiklikleri Alembic ile yönetilir (`create_all()` mevcut tablolara sütun eklemez).

```bash
# Yeni / boş veritabanı:
python init_db.py && alembic stamp head

# Mevcut veritabanını güncelle (bekleyen migration'ları uygula):
alembic upgrade head

# Model değiştikten sonra yeni migration üret:
alembic revision --autogenerate -m "açıklama" && alembic upgrade head
```

### 4. Çalıştırma

**Önerilen (Windows) — tek tıkla her şeyi başlatır:**
PostgreSQL servisi + Ollama (serve & model indirme) + DB init + FastAPI (:8000) + Next.js (:3000).

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Alternatifler:

```bash
python start.py   # cross-platform; PostgreSQL/Ollama'yı başlatmaz
python run.py     # yalnızca FastAPI (:8000)
```

Dashboard: http://localhost:3000 · Swagger UI: http://localhost:8000/docs

---

## 📡 API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/` | Agent durumu |
| `GET` | `/health` | Servis sağlığı (DB, Ollama, GitHub, Docker) |
| `GET` | `/agent/stats` | İstatistikler |
| `POST` | `/agent/trigger?task_type=...` | Manuel görev tetikleme |
| `GET` | `/agent/pending-actions` | Onay bekleyen kod değişiklikleri |
| `GET` | `/agent/pending-comments` | Onay bekleyen yorumlar |
| `POST` | `/agent/approve-action/{id}` | Kod değişikliği onayla → PR aç |
| `POST` | `/agent/reject-action/{id}` | Kod değişikliği reddet |
| `POST` | `/agent/approve-comment/{id}` | Yorum onayla → GitHub'a gönder |
| `POST` | `/agent/reject-comment/{id}` | Yorum reddet |
| `GET` | `/agent/actions?limit=20` | Aksiyon geçmişi |

---

## ⚙️ Yapılandırma Seçenekleri

| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `OLLAMA_MODEL` | `qwen3-coder:30b` | AI modeli |
| `TRENDING_DAYS_AGO` | `7` | Kaç gün öncesine kadar repo ara |
| `MIN_STARS_THRESHOLD` | `50` | Minimum yıldız sayısı |
| `LOOP_INTERVAL_SECONDS` | `3600` | Ana döngü aralığı (saniye) |
| `TASK_CONCURRENCY` | `3` | Paralel repo işleme sayısı |
| `REQUIRE_APPROVAL_FOR_PR` | `true` | PR için onay gerekli mi |
| `REQUIRE_APPROVAL_FOR_COMMENT` | `true` | Yorum için onay gerekli mi |

---

## 📁 Proje Yapısı

```
github-agent/
├── agent/
│   ├── orchestrator.py      # Ana orkestratör (6 phase pipeline)
│   ├── providers/           # Değiştirilebilir LLM provider'ları (Groq/Ollama/HF)
│   ├── ai/                  # AIReasoningService (provider-bağımsız akıl yürütme)
│   └── tools/
│       ├── github_client.py  # GitHub API (GraphQL + REST)
│       ├── chroma_client.py  # RAG pipeline
│       └── docker_env.py     # Docker sandbox
├── api/
│   └── main.py              # FastAPI endpoint'leri
├── core/
│   └── config.py            # Konfigürasyon
├── database/
│   ├── models.py            # 6 SQLAlchemy modeli
│   └── session.py           # DB bağlantı yönetimi
├── workspace/               # Klonlanan repolar (otomatik)
├── chroma_db/               # Vektör DB (otomatik)
├── alembic/                 # DB şema migration'ları (Alembic)
├── run.py                   # Başlatma
├── init_db.py               # DB tabloları oluşturma (bootstrap)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

*Powered by Groq / Ollama (swappable LLM) + GitHub GraphQL API + ChromaDB + Docker*
