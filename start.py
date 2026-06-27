# -*- coding: utf-8 -*-
"""
GitHub AI Agent - Tek Tıkla Başlatıcı.

Bu dosyayı çalıştırın, gerisini o halletsin:
  1. ✅ Ön kontroller (.env, GITHUB_TOKEN, Ollama)
  2. ✅ Veritabanı tablolarını oluştur/güncelle
  3. ✅ FastAPI sunucusunu arka planda başlat
  4. ✅ Sunucunun hazır olmasını bekle
  5. ✅ Dashboard'u tarayıcıda aç
  6. ✅ Sunucuları canlı tut (Ctrl+C ile çıkış)

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


TOTAL_STEPS = 6
VENV_PYTHON = os.path.join("venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join("venv", "bin", "python")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
server_process = None
dashboard_process = None
LOG_DIR = os.path.join(PROJECT_DIR, "logs")
SERVER_LOG = os.path.join(LOG_DIR, "server.log")
DASHBOARD_LOG = os.path.join(LOG_DIR, "dashboard.log")
_log_handles = []
STARTUP_TIMEOUT = 120  # saniye (soguk Next.js derlemesi yavas olabilir)


def _terminate(proc):
    """Bir process'i alt sürec agaciyla birlikte sonlandir.

    npm.cmd, gercek next-dev node cocuklarini birakir; sadece terminate()
    cagirmak bunlari orphan olarak birakir ve portlari dolu tutar.
    Windows'ta tum agaci taskkill /T ile kapatmak bunu onler.
    """
    if not proc or proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _tail(path, lines=20):
    """Log dosyasinin son satirlarini dondur (hata teshisi icin)."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return "".join(f.readlines()[-lines:]).strip()
    except OSError:
        return ""


def cleanup(signum=None, frame=None, code=0):
    """Çıkışta sunucuları (ve alt süreçlerini) kapat."""
    global server_process, dashboard_process
    print(f"\n  {C.DIM}🛑 Sunucular kapatılıyor...{C.RESET}")
    for p in [server_process, dashboard_process]:
        _terminate(p)
    for h in _log_handles:
        try:
            h.close()
        except OSError:
            pass
    print(f"\n  {C.GREEN}👋 Görüşmek üzere!{C.RESET}\n")
    sys.exit(code)


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

    os.makedirs(LOG_DIR, exist_ok=True)
    log = open(SERVER_LOG, "w", encoding="utf-8")
    _log_handles.append(log)

    # Çıktıyı log dosyasına yönlendir — dolan PIPE buffer'ı child'ı bloke ederdi.
    server_process = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"],
        cwd=PROJECT_DIR,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )
    ok("(PID: {})".format(server_process.pid))


def start_dashboard():
    """4. Next.js Dashboard sunucusunu başlat."""
    global dashboard_process
    step(4, TOTAL_STEPS, "Next.js Dashboard başlatılıyor...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    dashboard_dir = os.path.join(PROJECT_DIR, "dashboard")

    os.makedirs(LOG_DIR, exist_ok=True)
    log = open(DASHBOARD_LOG, "w", encoding="utf-8")
    _log_handles.append(log)

    # Çıktıyı log dosyasına yönlendir — Next.js bol çıktı üretir, PIPE dolarsa kilitlenir.
    dashboard_process = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=dashboard_dir,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    ok("(PID: {})".format(dashboard_process.pid))


def wait_for_servers():
    """5. Sunucuların hazır olmasını bekle."""
    step(5, TOTAL_STEPS, "Sunucuların hazır olması bekleniyor...")
    import urllib.request

    api_ready = False
    dash_ready = False
    deadline = time.time() + STARTUP_TIMEOUT

    while time.time() < deadline:
        if not api_ready:
            try:
                if urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=1).status == 200:
                    api_ready = True
            except Exception:
                pass

        if not dash_ready:
            try:
                if urllib.request.urlopen("http://127.0.0.1:3000/", timeout=1).status == 200:
                    dash_ready = True
            except Exception:
                pass

        if api_ready and dash_ready:
            ok()
            return True

        # Bir süreç çöktüyse log'un sonunu göster ve düzgün temizlen.
        if server_process and server_process.poll() is not None:
            fail("FastAPI sunucusu çöktü!")
            print(f"    {C.RED}{_tail(SERVER_LOG)}{C.RESET}")
            cleanup(code=1)

        if dashboard_process and dashboard_process.poll() is not None:
            fail("Next.js sunucusu çöktü!")
            print(f"    {C.RED}{_tail(DASHBOARD_LOG)}{C.RESET}")
            cleanup(code=1)

        time.sleep(1)

    fail(f"Sunucular {STARTUP_TIMEOUT}s içinde yanıt vermedi")
    if not api_ready:
        print(f"    {C.YELLOW}API logu (logs/server.log):{C.RESET}\n{_tail(SERVER_LOG)}")
    if not dash_ready:
        print(f"    {C.YELLOW}Dashboard logu (logs/dashboard.log):{C.RESET}\n{_tail(DASHBOARD_LOG)}")
    cleanup(code=1)


def serve_forever():
    """6. Dashboard'u aç ve sunucuları canlı tut; Ctrl+C ile kapat."""
    step(6, TOTAL_STEPS, "Sunucular hazır.\n")
    url = "http://localhost:3000/"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"  {C.DIM}─────────────────────────────────────────{C.RESET}")
    print(f"  {C.GREEN}Dashboard: {url}{C.RESET}")
    print(f"  {C.GREEN}API Docs : http://localhost:8000/docs{C.RESET}")
    print(f"  {C.DIM}Loglar   : logs/server.log, logs/dashboard.log{C.RESET}")
    print(f"  {C.DIM}Kapatmak için Ctrl+C.{C.RESET}")
    print(f"  {C.DIM}─────────────────────────────────────────{C.RESET}\n")

    # Süreçleri canlı tut; signal handler (cleanup) çıkışı yönetir.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


def main():
    os.chdir(PROJECT_DIR)
    print_banner()

    check_prerequisites()
    init_database()
    start_server()
    start_dashboard()
    wait_for_servers()
    serve_forever()


if __name__ == "__main__":
    main()
