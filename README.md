# GitHub Autonomous AI Agent

[![CI](https://github.com/Yigtwxx/github-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Yigtwxx/github-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Next.js](https://img.shields.io/badge/next.js-16-black)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An autonomous AI agent that **automatically discovers** trending GitHub repositories, **generates AI answers** to community questions (Issues & Discussions), and **creates real code patches and opens PRs** for solvable issues — all gated behind a human-in-the-loop approval workflow.

---

## ✨ Features

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
┌──────────────────────────────────────────────┐
│             FastAPI (api/main.py)            │
│  /health  /stats  /pending  /approve  /...   │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│              Agent Orchestrator              │
│              6-phase pipeline:               │
│    Trend Hunt → Repo Setup → Community →     │
│  Discussions → Issue Solving → PR Pipeline   │
└─────┬─────────┬──────────┬──────────┬────────┘
      │         │          │          │
┌─────▼────┐ ┌──▼───────┐ ┌▼────────┐ ┌▼───────┐
│  GitHub  │ │   LLM    │ │   RAG   │ │ Docker │
│  Client  │ │Providers │ │ChromaDB │ │Sandbox │
│(GQL+REST)│ │Groq/Olla.│ │         │ │        │
└──────────┘ └──────────┘ └─────────┘ └────────┘
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

**Single entry point — starts everything with one click:**
PostgreSQL service + Ollama (serve & model pull) + DB init + FastAPI (:8000) + Next.js (:3000).

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

FastAPI only (e.g. for API debugging):

```powershell
venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000
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
│   ├── orchestrator.py      # Main orchestrator (6-phase pipeline)
│   ├── ai/                  # AIReasoningService (provider-agnostic reasoning)
│   ├── providers/           # Swappable LLM providers (Groq / Ollama / HF)
│   ├── prompts/             # Jinja2 prompt templates
│   ├── rag/                 # Chunking, retrieval, reranking
│   ├── scoring/             # Repo & issue prioritization
│   ├── solver/              # Agentic code-fix loop (patch + verify)
│   ├── trends/              # Trend aggregation (GitHub, HN, Reddit)
│   └── tools/
│       ├── github_client.py # GitHub API (GraphQL + REST)
│       ├── chroma_client.py # ChromaDB indexing & search
│       └── docker_env.py    # Docker sandbox
├── api/
│   └── main.py              # FastAPI endpoints
├── core/
│   └── config.py            # Pydantic settings (.env)
├── database/
│   ├── models.py            # SQLAlchemy models
│   └── session.py           # DB connection management
├── dashboard/               # Next.js approval & monitoring UI
├── alembic/                 # DB schema migrations
├── tests/                   # Pytest suite
├── .github/workflows/       # CI (lint + typecheck + tests + build)
├── start.ps1                # One-click launcher (single entry point)
├── init_db.py               # DB bootstrap
├── pyproject.toml           # Ruff + pytest config
└── requirements.txt
```

---

## 📄 License

Released under the [MIT License](LICENSE).

---

*Powered by Groq / Ollama (swappable LLM) + GitHub GraphQL API + ChromaDB + Docker*
