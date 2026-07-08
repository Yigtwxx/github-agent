#  GitHub Autonomous AI Agent v2.0

An autonomous AI agent that **automatically discovers** trending GitHub repositories, **generates AI answers** to community questions (Issues & Discussions), and **creates real code patches and opens PRs** for solvable issues.

---

##  Features

| Feature | Description |
|---|---|
| 🔍 **Trend Hunter** | Discovers trending repos in 5 languages (Python, JS, TS, Go, Rust) and scores them by priority |
| 💬 **Issue Support** | Analyzes issues and generates AI answers with RAG context |
| 🗣️ **Discussion Support** | Automatically generates replies to GitHub Discussions |
| 🔧 **Issue Solver** | Solvability analysis → real code patch generation → syntax check → Docker sandbox test |
| 🚀 **Autonomous PR** | Fork → Branch → Commit → PR pipeline |
| 🛡️ **Human Approval** | All comments and PRs wait for approval before being sent |
| 📚 **RAG Pipeline** | Clone repo → index into ChromaDB → smart code search in issue context |
| 🐳 **Docker Sandbox** | Tests AI-generated code in an isolated environment |
| ⚡ **Rate Limiting** | Automatically manages GitHub API limits |

---

## 🛠️ Architecture

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

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+**
- **PostgreSQL** (data storage)
- **Ollama** + the `qwen3-coder:30b` model
- **Docker** (for sandbox tests)
- **Git** (for cloning repos)

### 1. Installation

```bash
# Virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
# source venv/bin/activate     # Linux/Mac

# Dependencies
pip install -r requirements.txt

# Ollama model (start.ps1 pulls this automatically; you can also do it manually)
ollama pull qwen3-coder:30b
```

### 2. Configuration

```bash
copy .env.example .env    # Windows
# cp .env.example .env    # Linux/Mac
```

Edit the `.env` file:
- `GITHUB_TOKEN` → [Create a GitHub PAT](https://github.com/settings/tokens) (required scopes: `repo`, `read:discussion`, `write:discussion`)
- `POSTGRES_*` → PostgreSQL connection details

### 3. Database

Schema changes are managed with Alembic (`create_all()` does not add columns to existing tables).

```bash
# Fresh / empty database:
python init_db.py && alembic stamp head

# Update an existing database (apply pending migrations):
alembic upgrade head

# Generate a new migration after changing a model:
alembic revision --autogenerate -m "description" && alembic upgrade head
```

### 4. Running

**Recommended (Windows) — starts everything with one click:**
PostgreSQL service + Ollama (serve & model pull) + DB init + FastAPI (:8000) + Next.js (:3000).

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Alternatives:

```bash
python start.py   # cross-platform; does NOT start PostgreSQL/Ollama
python run.py     # FastAPI only (:8000)
```

Dashboard: http://localhost:3000 · Swagger UI: http://localhost:8000/docs

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Agent status |
| `GET` | `/health` | Service health (DB, Ollama, GitHub, Docker) |
| `GET` | `/agent/stats` | Statistics |
| `POST` | `/agent/trigger?task_type=...` | Trigger a task manually |
| `GET` | `/agent/pending-actions` | Code changes awaiting approval |
| `GET` | `/agent/pending-comments` | Comments awaiting approval |
| `POST` | `/agent/approve-action/{id}` | Approve code change → open PR |
| `POST` | `/agent/reject-action/{id}` | Reject code change |
| `POST` | `/agent/approve-comment/{id}` | Approve comment → post to GitHub |
| `POST` | `/agent/reject-comment/{id}` | Reject comment |
| `GET` | `/agent/actions?limit=20` | Action history |

---

## ⚙️ Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen3-coder:30b` | AI model |
| `TRENDING_DAYS_AGO` | `7` | How many days back to search for repos |
| `MIN_STARS_THRESHOLD` | `50` | Minimum star count |
| `LOOP_INTERVAL_SECONDS` | `3600` | Main loop interval (seconds) |
| `TASK_CONCURRENCY` | `3` | Number of repos processed in parallel |
| `REQUIRE_APPROVAL_FOR_PR` | `true` | Whether PRs require approval |
| `REQUIRE_APPROVAL_FOR_COMMENT` | `true` | Whether comments require approval |

---

## 📁 Project Structure

```
github-agent/
├── agent/
│   ├── orchestrator.py      # Main orchestrator (6 phase pipeline)
│   ├── providers/           # Swappable LLM providers (Groq/Ollama/HF)
│   ├── ai/                  # AIReasoningService (provider-agnostic reasoning)
│   └── tools/
│       ├── github_client.py  # GitHub API (GraphQL + REST)
│       ├── chroma_client.py  # RAG pipeline
│       └── docker_env.py     # Docker sandbox
├── api/
│   └── main.py              # FastAPI endpoints
├── core/
│   └── config.py            # Configuration
├── database/
│   ├── models.py            # 6 SQLAlchemy models
│   └── session.py           # DB connection management
├── workspace/               # Cloned repos (auto-generated)
├── chroma_db/               # Vector DB (auto-generated)
├── alembic/                 # DB schema migrations (Alembic)
├── run.py                   # Entry point
├── init_db.py               # DB table creation (bootstrap)
├── requirements.txt
├── .env.example
└── .gitignore
```

---

*Powered by Groq / Ollama (swappable LLM) + GitHub GraphQL API + ChromaDB + Docker*
