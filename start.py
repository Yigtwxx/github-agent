# -*- coding: utf-8 -*-
"""
GitHub AI Agent - Tek Tıkla Başlatıcı.

Bu dosyayı çalıştırın, gerisini o halletsin:
  1. ✅ Ön kontroller (.env, GITHUB_TOKEN, Ollama)
  2. ✅ Veritabanı tablolarını oluştur/güncelle
  3. ✅ FastAPI sunucusunu arka planda başlat
  4. ✅ Sunucunun hazır olmasını bekle
  5. ✅ Dashboard'u tarayıcıda aç
  6. ✅ Terminal CLI'ı başlat (interaktif kontrol)

Kullanım:
  python start.py
"""
import os
import sys
import time
import signal
import subprocess
import webbrowser
import threading

# ── Renk kodları (cross-platform) ──
class C:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def print_banner():
    print(f"""
{C.CYAN}{C.BOLD}╔══════════════════════════════════════════════════╗
║          🤖 GitHub AI Agent - Başlatıcı          ║
╚══════════════════════════════════════════════════╝{C.RESET}
    """)


def step(num, total, msg):
    print(f"  {C.CYAN}[{num}/{total}]{C.RESET} {msg}", end="", flush=True)


def ok(extra=""):
    print(f" {C.GREEN}✓{C.RESET}{' ' + extra if extra else ''}")


def fail(msg):
    print(f" {C.RED}✗ {msg}{C.RESET}")


def warn(msg):
    print(f"  {C.YELLOW}⚠ {msg}{C.RESET}")


TOTAL_STEPS = 7
VENV_PYTHON = os.path.join("venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join("venv", "bin", "python")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
server_process = None
dashboard_process = None


def cleanup(signum=None, frame=None):
    """Çıkışta sunucuyu kapat."""
    global server_process, dashboard_process
    print(f"\n  {C.DIM}🛑 Sunucular kapatılıyor...{C.RESET}")
    for p in [server_process, dashboard_process]:
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
    print(f"\n  {C.GREEN}👋 Görüşmek üzere!{C.RESET}\n")
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)


def check_prerequisites():
    """1. Ön kontroller."""
    step(1, TOTAL_STEPS, "Ön kontroller yapılıyor...")
    errors = []

    # .env dosyası
    if not os.path.exists(os.path.join(PROJECT_DIR, ".env")):
        errors.append(".env dosyası bulunamadı! .env.example dosyasını kopyalayın.")

    # GITHUB_TOKEN
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_DIR, ".env"))

    if not os.environ.get("GITHUB_TOKEN"):
        errors.append("GITHUB_TOKEN ayarlanmamış! .env dosyasını düzenleyin.")

    # Python venv
    python_exe = os.path.join(PROJECT_DIR, VENV_PYTHON)
    if not os.path.exists(python_exe):
        errors.append(f"Virtual environment bulunamadı ({VENV_PYTHON}). 'python -m venv venv' çalıştırın.")

    if errors:
        fail("Ön kontroller başarısız!")
        for e in errors:
            print(f"    {C.RED}• {e}{C.RESET}")
        sys.exit(1)

    ok()


def init_database():
    """2. Veritabanı tabloları."""
    step(2, TOTAL_STEPS, "Veritabanı tabloları oluşturuluyor...")
    python_exe = os.path.join(PROJECT_DIR, VENV_PYTHON)
    result = subprocess.run(
        [python_exe, "init_db.py"],
        cwd=PROJECT_DIR,
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        fail("Veritabanı başlatılamadı!")
        print(f"    {C.RED}{result.stderr[:300]}{C.RESET}")
        sys.exit(1)
    ok()


def start_server():
    """3. FastAPI sunucusunu arka planda başlat."""
    global server_process
    step(3, TOTAL_STEPS, "FastAPI sunucusu başlatılıyor...")
    python_exe = os.path.join(PROJECT_DIR, VENV_PYTHON)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # Sunucuyu arka plan işlemi olarak başlat
    server_process = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"],
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    ok("(PID: {})".format(server_process.pid))


def start_dashboard():
    """4. Next.js Dashboard sunucusunu başlat."""
    global dashboard_process
    step(4, TOTAL_STEPS, "Next.js Dashboard başlatılıyor...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    dashboard_dir = os.path.join(PROJECT_DIR, "dashboard")

    # Next.js sunucusunu arka planda başlat
    dashboard_process = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=dashboard_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ok("(PID: {})".format(dashboard_process.pid))


def wait_for_servers():
    """5. Sunucuların hazır olmasını bekle."""
    step(5, TOTAL_STEPS, "Sunucuların hazır olması bekleniyor...")
    import urllib.request

    api_ready = False
    dash_ready = False
    max_attempts = 45

    for i in range(max_attempts):
        # API kontrol
        if not api_ready:
            try:
                # /health yerine ana dizin yeterli
                req = urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=1)
                if req.status == 200:
                    api_ready = True
            except Exception:
                pass

        # Dashboard kontrol
        if not dash_ready:
            try:
                req = urllib.request.urlopen("http://127.0.0.1:3000/", timeout=1)
                if req.status == 200:
                    dash_ready = True
            except Exception:
                pass

        if api_ready and dash_ready:
            ok()
            return True

        if server_process and server_process.poll() is not None:
            fail("FastAPI sunucusu çöktü!")
            stderr = server_process.stderr.read().decode('utf-8', errors='ignore') if server_process.stderr else ""
            if stderr:
                print(f"    {C.RED}{stderr.strip()}{C.RESET}")
            sys.exit(1)
            
        if dashboard_process and dashboard_process.poll() is not None:
            fail("Next.js sunucusu çöktü!")
            stderr = dashboard_process.stderr.read().decode('utf-8', errors='ignore') if dashboard_process.stderr else ""
            if stderr:
                print(f"    {C.RED}{stderr.strip()}{C.RESET}")
            sys.exit(1)

        time.sleep(1)

    fail("Sunucular yanıt vermedi (45s timeout)")
    sys.exit(1)


def open_dashboard():
    """6. Dashboard'u tarayıcıda aç."""
    step(6, TOTAL_STEPS, "Dashboard tarayıcıda açılıyor...")
    url = "http://localhost:3000/"
    try:
        webbrowser.open(url)
        ok(url)
    except Exception:
        warn(f"Tarayıcı açılamadı. Manuel: {url}")


def launch_cli():
    """7. Terminal CLI'ı başlat."""
    step(7, TOTAL_STEPS, "Terminal CLI başlatılıyor...\n")
    print(f"  {C.DIM}─────────────────────────────────────────{C.RESET}")
    print(f"  {C.GREEN}Sunucular arka planda çalışıyor.{C.RESET}")
    print(f"  {C.GREEN}Dashboard: http://localhost:3000/{C.RESET}")
    print(f"  {C.GREEN}API Docs : http://localhost:8000/docs{C.RESET}")
    print(f"  {C.DIM}CLI'dan çıkmak = sunucular da kapanır.{C.RESET}")
    print(f"  {C.DIM}─────────────────────────────────────────{C.RESET}\n")

    # CLI'ı aynı süreçte çalıştır (interaktif olması için)
    python_exe = os.path.join(PROJECT_DIR, VENV_PYTHON)
    try:
        cli_result = subprocess.run(
            [python_exe, "cli.py"],
            cwd=PROJECT_DIR,
        )
    except KeyboardInterrupt:
        pass

    cleanup()


def main():
    os.chdir(PROJECT_DIR)
    print_banner()

    check_prerequisites()
    init_database()
    start_server()
    start_dashboard()
    wait_for_servers()
    open_dashboard()
    launch_cli()


if __name__ == "__main__":
    main()
