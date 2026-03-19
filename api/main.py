"""
FastAPI Uygulama Katmanı - Agent kontrol paneli.

Endpoint'ler:
  GET  /              → Durum
  GET  /health        → Servis sağlığı
  GET  /agent/stats   → İstatistikler
  POST /agent/trigger → Manuel görev tetikleme
  GET  /agent/pending-actions  → Onay bekleyen kod değişiklikleri
  GET  /agent/pending-comments → Onay bekleyen yorumlar
  POST /agent/approve-action/{id}  → Kod değişikliği onayla
  POST /agent/reject-action/{id}   → Kod değişikliği reddet
  POST /agent/approve-comment/{id} → Yorum onayla
  POST /agent/reject-comment/{id}  → Yorum reddet
  GET  /agent/actions  → Son aksiyonlar
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings
from database.session import engine, Base, get_db
from database.models import AgentActionHistory, AgentComment, CodePatch, Repo, Issue
from agent.orchestrator import AgentOrchestrator


# Tabloları oluştur
Base.metadata.create_all(bind=engine)

# Orkestratör
orchestrator = AgentOrchestrator()


def _log_task_error(task: asyncio.Task, context: str):
    """Background task exception'larını loglar."""
    if not task.cancelled() and task.exception():
        logger.error(f"Background task '{context}' başarısız: {task.exception()}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlatma / kapatma."""
    print(f"\n{'═'*50}")
    print(f"  🤖 {settings.PROJECT_NAME}")
    print(f"  📡 API     : http://localhost:8000/docs")
    print(f"  🖥️  Dashboard: http://localhost:3000/ (Next.js)")
    print(f"  🧠 Model   : {settings.OLLAMA_MODEL}")
    print(f"{'═'*50}\n")

    loop_task = asyncio.create_task(orchestrator.run_autonomous_loop())
    yield
    print("\n🛑 Agent durduruluyor...")
    orchestrator.is_running = False
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Otonom GitHub AI Agent - Kontrol Paneli",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════
#  DURUM & SAĞLIK
# ══════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {
        "message": f"{settings.PROJECT_NAME} çalışıyor.",
        "status": orchestrator.status,
        "stats": orchestrator.stats,
    }


@app.get("/health")
async def health_check():
    """Tüm servislerin sağlığını kontrol eder."""
    health = {
        "agent": orchestrator.status,
        "database": "unknown",
        "ollama": "unknown",
        "github": "unknown",
        "docker": "available" if orchestrator.sandbox.available else "unavailable",
        "chromadb": "available" if orchestrator.rag.client else "unavailable",
    }

    # DB
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        health["database"] = "healthy"
        db.close()
    except Exception:
        health["database"] = "unhealthy"

    # GitHub
    try:
        user = await orchestrator.github.get_authenticated_user()
        health["github"] = f"authenticated ({user})" if user else "unauthenticated"
    except Exception:
        health["github"] = "unreachable"

    return health


@app.get("/agent/stats")
def get_stats():
    """Agent istatistiklerini döndürür."""
    return {
        "status": orchestrator.status,
        "is_running": orchestrator.is_running,
        **orchestrator.stats,
    }


# ══════════════════════════════════════════════════════════
#  MANUEL TETİKLEME
# ══════════════════════════════════════════════════════════

@app.post("/agent/trigger")
async def trigger_task(task_type: str):
    """
    Manuel görev tetikleme.
    task_type: trend_hunt | community_support | discussion_support | issue_solving | repo_setup
    """
    task_map = {
        "trend_hunt": orchestrator._phase_trend_hunt,
        "community_support": orchestrator._phase_community_support,
        "discussion_support": orchestrator._phase_discussion_support,
        "issue_solving": orchestrator._phase_issue_solving,
        "repo_setup": orchestrator._phase_repo_setup,
    }

    if task_type not in task_map:
        raise HTTPException(
            status_code=400,
            detail=f"Geçersiz görev tipi. Geçerli seçenekler: {list(task_map.keys())}",
        )

    task = asyncio.create_task(task_map[task_type]())
    task.add_done_callback(lambda t: _log_task_error(t, f"trigger:{task_type}"))
    return {"message": f"'{task_type}' görevi arka planda başlatıldı."}


# ══════════════════════════════════════════════════════════
#  ONAY BEKLEYENLERİ LİSTELE
# ══════════════════════════════════════════════════════════

@app.get("/agent/pending-actions")
async def list_pending_actions(db: Session = Depends(get_db)):
    """Onay bekleyen kod değişikliklerini listeler."""
    def get_actions():
        actions = (
            db.query(AgentActionHistory)
            .filter(AgentActionHistory.status == "AWAITING_APPROVAL")
            .order_by(AgentActionHistory.created_at.desc())
            .all()
        )
        result = []
        for a in actions:
            repo = db.query(Repo).filter(Repo.id == a.repo_id).first()
            patches = db.query(CodePatch).filter(CodePatch.action_id == a.id).all()
            result.append({
                "id": a.id,
                "repo": f"{repo.owner}/{repo.name}" if repo else "N/A",
                "action_type": a.action_type,
                "branch": a.proposed_branch,
                "commit_message": a.commit_message,
                "sandbox_test": a.sandbox_test_passed,
                "details": a.details,
                "patches": [
                    {
                        "file": p.file_path,
                        "diff": p.diff_text,
                        "content_preview": p.patched_content[:500] if p.patched_content else "",
                    }
                    for p in patches
                ],
                "created_at": str(a.created_at),
            })
        return result
    return await asyncio.to_thread(get_actions)


@app.get("/agent/pending-comments")
async def list_pending_comments(db: Session = Depends(get_db)):
    """Onay bekleyen yorumları listeler."""
    def get_comments():
        comments = (
            db.query(AgentComment)
            .filter(AgentComment.status == "AWAITING_APPROVAL")
            .order_by(AgentComment.created_at.desc())
            .all()
        )
        result = []
        for c in comments:
            repo = db.query(Repo).filter(Repo.id == c.repo_id).first()
            result.append({
                "id": c.id,
                "repo": f"{repo.owner}/{repo.name}" if repo else "N/A",
                "type": c.target_type,
                "target_number": c.target_number,
                "target_url": c.target_url,
                "body_preview": c.body[:500] if c.body else "",
                "created_at": str(c.created_at),
            })
        return result
    return await asyncio.to_thread(get_comments)


# ══════════════════════════════════════════════════════════
#  ONAYLA / REDDET
# ══════════════════════════════════════════════════════════

@app.post("/agent/approve-action/{action_id}")
async def approve_action(action_id: int, db: Session = Depends(get_db)):
    """Kod değişikliğini onaylar → PR süreci başlatır."""
    action = db.query(AgentActionHistory).filter(AgentActionHistory.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Aksiyon bulunamadı")
    if action.status != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail=f"Aksiyon zaten '{action.status}' durumunda.")

    action.status = "APPROVED"
    db.commit()
    task = asyncio.create_task(orchestrator.process_approved_action(action_id))
    task.add_done_callback(lambda t: _log_task_error(t, f"approve_action:{action_id}"))
    return {"message": f"Aksiyon #{action_id} onaylandı. PR süreci başlatılıyor."}


@app.post("/agent/reject-action/{action_id}")
def reject_action(action_id: int, db: Session = Depends(get_db)):
    action = db.query(AgentActionHistory).filter(AgentActionHistory.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Aksiyon bulunamadı")
    if action.status != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail=f"Aksiyon zaten '{action.status}' durumunda.")
    action.status = "REJECTED"
    db.commit()
    return {"message": f"Aksiyon #{action_id} reddedildi."}


@app.post("/agent/approve-comment/{comment_id}")
async def approve_comment(comment_id: int, db: Session = Depends(get_db)):
    """Yorumu onaylar → GitHub'a gönderir."""
    comment = db.query(AgentComment).filter(AgentComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    if comment.status != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail=f"Yorum zaten '{comment.status}' durumunda.")

    comment.status = "APPROVED"
    db.commit()
    task = asyncio.create_task(orchestrator.process_approved_comment(comment_id))
    task.add_done_callback(lambda t: _log_task_error(t, f"approve_comment:{comment_id}"))
    return {"message": f"Yorum #{comment_id} onaylandı. GitHub'a gönderiliyor."}


@app.post("/agent/reject-comment/{comment_id}")
def reject_comment(comment_id: int, db: Session = Depends(get_db)):
    comment = db.query(AgentComment).filter(AgentComment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    if comment.status != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail=f"Yorum zaten '{comment.status}' durumunda.")
    comment.status = "REJECTED"
    db.commit()
    return {"message": f"Yorum #{comment_id} reddedildi."}


# ══════════════════════════════════════════════════════════
#  AKSİYON GEÇMİŞİ
# ══════════════════════════════════════════════════════════

@app.get("/agent/actions")
async def list_actions(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Son aksiyonları listeler."""
    def get_recent_actions():
        actions = (
            db.query(AgentActionHistory)
            .order_by(AgentActionHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        result = []
        for a in actions:
            repo = db.query(Repo).filter(Repo.id == a.repo_id).first()
            result.append({
                "id": a.id,
                "repo": f"{repo.owner}/{repo.name}" if repo else "N/A",
                "action_type": a.action_type,
                "status": a.status,
                "pr_url": a.pr_url,
                "details": a.details,
                "created_at": str(a.created_at),
                "completed_at": str(a.completed_at) if a.completed_at else None,
            })
        return result
    return await asyncio.to_thread(get_recent_actions)
