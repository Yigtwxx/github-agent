"""
GitHub AI Agent - İnteraktif Terminal Kontrol Paneli (CLI).

Kullanım: python cli.py

Bu terminal arayüzü üzerinden:
  • Agent durumunu görüntüleyin
  • Onay bekleyen kod değişikliklerini inceleyin ve onaylayın/reddedin
  • Onay bekleyen yorumları inceleyin ve onaylayın/reddedin
  • Görevleri manuel tetikleyin
  • Aksiyon geçmişini görüntüleyin
"""
import sys
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich import box

console = Console()

API_BASE = "http://127.0.0.1:8000"


def api_get(path: str):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=30)
        return r.json()
    except requests.ConnectionError:
        console.print("[red bold]❌ Agent sunucusuna bağlanılamadı![/]")
        console.print(f"[dim]   Sunucu çalışıyor mu? → python run.py[/]")
        return None
    except Exception as e:
        console.print(f"[red]Hata: {e}[/]")
        return None


def api_post(path: str):
    try:
        r = requests.post(f"{API_BASE}{path}", timeout=30)
        return r.json()
    except requests.ConnectionError:
        console.print("[red bold]❌ Sunucuya bağlanılamadı![/]")
        return None
    except Exception as e:
        console.print(f"[red]Hata: {e}[/]")
        return None


# ══════════════════════════════════════════════════════════
#  MENÜ AKIŞLARI
# ══════════════════════════════════════════════════════════

def show_banner():
    banner = Text()
    banner.append("🤖 GitHub AI Agent", style="bold cyan")
    banner.append(" — Terminal Kontrol Paneli", style="dim")
    console.print(Panel(banner, border_style="cyan", padding=(0, 2)))


def show_status():
    """Agent durumu ve istatistikleri göster."""
    data = api_get("/")
    if not data:
        return

    health = api_get("/health")

    # Durum paneli
    status_text = Text()
    status_emoji = {"RUNNING": "🟢", "SLEEPING": "💤", "IDLE": "⚪", "STOPPED": "🔴"}.get(
        data.get("status", ""), "🔵"
    )
    status_text.append(f"\n  Durum  : {status_emoji} {data.get('status', 'N/A')}\n")

    stats = data.get("stats", {})
    status_text.append(f"  Döngü  : {stats.get('cycles_completed', 0)} tamamlandı\n")
    status_text.append(f"  Repolar: {stats.get('repos_discovered', 0)} keşfedildi\n")
    status_text.append(f"  Issue  : {stats.get('issues_analyzed', 0)} analiz edildi\n")
    status_text.append(f"  Discuss: {stats.get('discussions_analyzed', 0)} analiz edildi\n")
    status_text.append(f"  Yorumlar: {stats.get('comments_generated', 0)} üretildi\n")
    status_text.append(f"  PR'lar : {stats.get('prs_created', 0)} oluşturuldu\n")

    console.print(Panel(status_text, title="[bold]📊 Agent Durumu[/]", border_style="green"))

    # Sağlık tablosu
    if health:
        table = Table(title="🏥 Servis Sağlığı", box=box.ROUNDED, border_style="blue")
        table.add_column("Servis", style="bold")
        table.add_column("Durum")

        for service, status in health.items():
            color = "green" if "healthy" in str(status).lower() or "available" in str(status).lower() or "authenticated" in str(status).lower() else "yellow"
            if "unhealthy" in str(status).lower() or "unreachable" in str(status).lower():
                color = "red"
            table.add_row(service, f"[{color}]{status}[/]")

        console.print(table)


def show_pending_actions():
    """Onay bekleyen kod değişikliklerini göster."""
    actions = api_get("/agent/pending-actions")
    if not actions:
        console.print("[dim]  Onay bekleyen kod değişikliği yok.[/]\n")
        return

    if len(actions) == 0:
        console.print("[dim]  Onay bekleyen kod değişikliği yok. ✨[/]\n")
        return

    for action in actions:
        # Başlık paneli
        header = Text()
        header.append(f"\n  ID     : {action['id']}\n", style="bold")
        header.append(f"  Repo   : {action['repo']}\n", style="cyan")
        header.append(f"  Branch : {action.get('branch', 'N/A')}\n")
        header.append(f"  Commit : {action.get('commit_message', 'N/A')}\n")

        sandbox = action.get('sandbox_test')
        if sandbox is not None:
            emoji = "✅" if sandbox else "❌"
            header.append(f"  Test   : {emoji} Docker Sandbox\n")

        details = action.get('details', {})
        if details:
            header.append(f"  Zorluk : {details.get('difficulty', 'N/A')}/10\n")
            header.append(f"  Özet   : {details.get('changes_summary', 'N/A')[:100]}\n")

        console.print(Panel(header, title=f"[bold yellow]⏳ Aksiyon #{action['id']}[/]", border_style="yellow"))

        # Patch'leri göster
        patches = action.get('patches', [])
        for patch in patches:
            console.print(f"  [bold]📄 {patch['file']}[/]")
            if patch.get('diff'):
                console.print(f"  [dim]{patch['diff']}[/]")
            if patch.get('content_preview'):
                console.print(Syntax(patch['content_preview'], "python", theme="monokai", line_numbers=False, word_wrap=True))
            console.print()

        # Onay sor
        choice = Prompt.ask(
            f"  [bold]Aksiyon #{action['id']}[/]",
            choices=["approve", "reject", "skip"],
            default="skip"
        )

        if choice == "approve":
            result = api_post(f"/agent/approve-action/{action['id']}")
            if result:
                console.print(f"  [green bold]✅ {result.get('message', 'Onaylandı')}[/]\n")

        elif choice == "reject":
            result = api_post(f"/agent/reject-action/{action['id']}")
            if result:
                console.print(f"  [red]❌ {result.get('message', 'Reddedildi')}[/]\n")

        else:
            console.print("  [dim]⏭ Atlanıyor...[/]\n")


def show_pending_comments():
    """Onay bekleyen yorumları göster."""
    comments = api_get("/agent/pending-comments")
    if not comments:
        console.print("[dim]  Onay bekleyen yorum yok.[/]\n")
        return

    if len(comments) == 0:
        console.print("[dim]  Onay bekleyen yorum yok. ✨[/]\n")
        return

    for comment in comments:
        target = f"{comment['type']} #{comment['target_number']}"
        header = Text()
        header.append(f"\n  ID    : {comment['id']}\n", style="bold")
        header.append(f"  Repo  : {comment['repo']}\n", style="cyan")
        header.append(f"  Hedef : {target}\n")
        if comment.get('target_url'):
            header.append(f"  URL   : {comment['target_url']}\n", style="dim")

        console.print(Panel(header, title=f"[bold yellow]💬 Yorum #{comment['id']}[/]", border_style="yellow"))

        # Yorum içeriğini markdown olarak render et
        body = comment.get('body_preview', '')
        if body:
            console.print(Panel(
                Markdown(body),
                title="[dim]Yorum İçeriği[/]",
                border_style="dim",
                padding=(1, 2),
            ))

        choice = Prompt.ask(
            f"  [bold]Yorum #{comment['id']}[/]",
            choices=["approve", "reject", "skip"],
            default="skip"
        )

        if choice == "approve":
            result = api_post(f"/agent/approve-comment/{comment['id']}")
            if result:
                console.print(f"  [green bold]✅ {result.get('message', 'Onaylandı')}[/]\n")

        elif choice == "reject":
            result = api_post(f"/agent/reject-comment/{comment['id']}")
            if result:
                console.print(f"  [red]❌ {result.get('message', 'Reddedildi')}[/]\n")

        else:
            console.print("  [dim]⏭ Atlanıyor...[/]\n")


def show_action_history():
    """Son aksiyonları göster."""
    actions = api_get("/agent/actions?limit=15")
    if not actions:
        return

    table = Table(
        title="📜 Son Aksiyonlar",
        box=box.ROUNDED,
        border_style="blue",
        show_lines=True,
    )
    table.add_column("#", style="bold", width=4)
    table.add_column("Repo", style="cyan", max_width=25)
    table.add_column("Tip", width=20)
    table.add_column("Durum", width=18)
    table.add_column("PR", max_width=40)
    table.add_column("Tarih", style="dim", width=16)

    status_colors = {
        "SUCCESS": "green", "FAILED": "red", "AWAITING_APPROVAL": "yellow",
        "APPROVED": "blue", "REJECTED": "red", "IN_PROGRESS": "cyan",
        "PENDING": "dim",
    }

    for a in actions:
        status = a.get("status", "")
        color = status_colors.get(status, "white")
        pr_url = a.get("pr_url", "") or ""
        date_str = a.get("created_at", "")[:16] if a.get("created_at") else ""

        table.add_row(
            str(a["id"]),
            a.get("repo", "N/A"),
            a.get("action_type", ""),
            f"[{color}]{status}[/]",
            pr_url[:40] if pr_url else "-",
            date_str,
        )

    console.print(table)


def trigger_task():
    """Manuel görev tetikleme."""
    console.print("\n[bold]Hangi görevi tetiklemek istiyorsunuz?[/]\n")
    tasks = {
        "1": ("trend_hunt", "🔍 Trend Avcısı - Popüler repoları keşfet"),
        "2": ("repo_setup", "📚 Repo Kurulum - Klonla + RAG indeksle"),
        "3": ("community_support", "💬 Community Support - Issue'lara cevap üret"),
        "4": ("discussion_support", "🗣️  Discussion Support - Discussion'lara cevap üret"),
        "5": ("issue_solving", "🔧 Issue Solver - Çözülebilir issue bul + kod üret"),
    }

    for key, (_, desc) in tasks.items():
        console.print(f"  [{key}] {desc}")

    choice = Prompt.ask("\n  Seçiminiz", choices=list(tasks.keys()) + ["q"], default="q")

    if choice == "q":
        return

    task_type, desc = tasks[choice]
    result = api_post(f"/agent/trigger?task_type={task_type}")
    if result:
        console.print(f"\n  [green bold]✅ '{task_type}' görevi tetiklendi![/]\n")


# ══════════════════════════════════════════════════════════
#  ANA MENÜ
# ══════════════════════════════════════════════════════════

def main_menu():
    """Ana menü döngüsü."""
    show_banner()

    while True:
        console.print()
        menu_table = Table(box=None, show_header=False, padding=(0, 2))
        menu_table.add_column(style="bold cyan", width=4)
        menu_table.add_column()

        menu_table.add_row("[1]", "📊 Agent Durumu & Sağlık")
        menu_table.add_row("[2]", "⏳ Onay Bekleyen Kod Değişiklikleri")
        menu_table.add_row("[3]", "💬 Onay Bekleyen Yorumlar")
        menu_table.add_row("[4]", "📜 Aksiyon Geçmişi")
        menu_table.add_row("[5]", "🚀 Manuel Görev Tetikle")
        menu_table.add_row("[q]", "🚪 Çıkış")

        console.print(Panel(menu_table, title="[bold]Ana Menü[/]", border_style="cyan", padding=(1, 1)))

        choice = Prompt.ask("  Seçiminiz", choices=["1", "2", "3", "4", "5", "q"], default="1")

        console.print()

        if choice == "1":
            show_status()
        elif choice == "2":
            show_pending_actions()
        elif choice == "3":
            show_pending_comments()
        elif choice == "4":
            show_action_history()
        elif choice == "5":
            trigger_task()
        elif choice == "q":
            console.print("[bold]👋 Görüşmek üzere![/]")
            break


if __name__ == "__main__":
    main_menu()
