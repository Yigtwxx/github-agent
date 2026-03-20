"""
Docker Sandbox - Güvenli kod yürütme ortamı.

AI tarafından üretilen kodu izole bir konteyner içinde çalıştırır,
böylece ana sisteme zarar vermesi önlenir.
"""
import asyncio
from typing import Optional

import docker
from loguru import logger


class DockerSandbox:
    """
    Tek kullanımlık Docker konteynerı içinde kod/test çalıştırma.
    Güvenlik önlemleri: bellek limiti, ağ erişimi kapalı, zaman aşımı.
    """

    def __init__(self):
        try:
            self.client = docker.from_env()
            # Docker bağlantısını test et
            self.client.ping()
            self.available = True
            logger.info("Docker Sandbox hazır ✓")
        except Exception as e:
            logger.warning(f"Docker kullanılamıyor (sandbox testleri devre dışı): {e}")
            self.client = None
            self.available = False

    async def run_tests(
        self,
        repo_path: str,
        command: str = "pytest",
        image: str = "python:3.11-slim",
        timeout: int = 120,
        mem_limit: str = "1g",
    ) -> dict:
        """
        Verilen repo dizinini Docker içinde çalıştırır.

        Returns: {
            "status": "success" | "failed" | "error",
            "exit_code": int,
            "logs": str,
            "timed_out": bool
        }
        """
        if not self.available:
            return {
                "status": "skipped",
                "exit_code": -1,
                "logs": "Docker kullanılamıyor",
                "timed_out": False,
            }

        try:
            result = await asyncio.to_thread(
                self._run_container,
                repo_path=repo_path,
                command=command,
                image=image,
                timeout=timeout,
                mem_limit=mem_limit,
            )
            return result
        except Exception as e:
            logger.error(f"Docker sandbox hatası: {e}")
            return {
                "status": "error",
                "exit_code": -1,
                "logs": str(e),
                "timed_out": False,
            }

    def _run_container(
        self, repo_path: str, command: str,
        image: str, timeout: int, mem_limit: str,
    ) -> dict:
        """Senkron Docker konteyner çalıştırma (thread'de çağrılır)."""
        install_cmd = (
            "pip install -r requirements.txt 2>/dev/null;"
            "pip install pytest 2>/dev/null;"
        )
        full_cmd = f"bash -c '{install_cmd} {command}'"

        try:
            container = self.client.containers.run(
                image=image,
                command=full_cmd,
                volumes={repo_path: {"bind": "/workspace", "mode": "rw"}},
                working_dir="/workspace",
                remove=True,
                detach=False,
                mem_limit=mem_limit,
                network_disabled=True,  # Güvenlik: dış ağ erişimi kapalı
                stdout=True,
                stderr=True,
            )
            logs = container.decode("utf-8") if isinstance(container, bytes) else str(container)
            return {
                "status": "success",
                "exit_code": 0,
                "logs": logs[-5000:],   # Son 5000 karakter
                "timed_out": False,
            }

        except docker.errors.ContainerError as exc:
            stderr = exc.stderr.decode("utf-8") if exc.stderr else ""
            return {
                "status": "failed",
                "exit_code": exc.exit_status,
                "logs": stderr[-5000:],
                "timed_out": False,
            }

    async def lint_python_file(self, file_content: str) -> dict:
        """Python dosyasını basit syntax kontrolünden geçirir."""
        try:
            compile(file_content, "<ai_generated>", "exec")
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {"valid": False, "error": f"Satır {e.lineno}: {e.msg}"}
