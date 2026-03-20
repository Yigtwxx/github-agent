"""
ChromaDB RAG Pipeline - Repo dosyalarını indeksle ve issue'lar için akıllı retrieval yap.

Özellikler:
  • Klonlanan repo dosyalarını otomatik chunk+indeksleme
  • Dosya uzantısına göre akıllı chunking
  • Metadata zenginleştirme (dosya yolu, dil, satır numaraları)
  • Issue/Discussion bağlamında relevant kod arama
"""
import os
from typing import Optional

import chromadb
from loguru import logger

from core.config import settings

# İndekslenecek dosya uzantıları
INDEXABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".go", ".rs",
    ".md", ".txt", ".yml", ".yaml", ".toml",
    ".json", ".cfg", ".ini",
    ".java", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".swift", ".kt",
    ".sh", ".bash", ".ps1",
    ".dockerfile", ".sql",
}

# Atlanan dizinler
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "vendor", ".next", "target", "bin", "obj",
}

# Maksimum dosya boyutu (bytes)
MAX_FILE_SIZE = 100_000  # 100KB


class ChromaDBManager:
    def __init__(self):
        try:
            self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)
            self.collection_name = "repo_knowledge"
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"ChromaDB hazır (Dizin: {settings.CHROMA_PERSIST_DIRECTORY})")
        except Exception as e:
            logger.error(f"ChromaDB başlatma hatası: {e}")
            self.client = None
            self.collection = None

    # ══════════════════════════════════════════════════════════
    #  REPO İNDEKSLEME
    # ══════════════════════════════════════════════════════════

    def index_repository(self, repo_full_name: str, clone_path: str) -> int:
        """
        Klonlanmış repo dizinini tara, dosyaları chunk'la ve ChromaDB'ye ekle.
        Returns: indekslenen chunk sayısı.
        """
        if not self.client:
            return 0

        documents = []
        metadatas = []
        ids = []
        chunk_count = 0

        for root, dirs, files in os.walk(clone_path):
            # Atlanacak dizinleri çıkar
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in INDEXABLE_EXTENSIONS:
                    continue

                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, clone_path).replace("\\", "/")

                try:
                    size = os.path.getsize(fpath)
                    if size > MAX_FILE_SIZE or size == 0:
                        continue

                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    if not content.strip():
                        continue

                    # Dosyayı chunk'la
                    chunks = self._chunk_file(content, ext, rel_path)

                    for i, chunk in enumerate(chunks):
                        doc_id = f"{repo_full_name}::{rel_path}::chunk_{i}"
                        documents.append(chunk["text"])
                        metadatas.append({
                            "repo": repo_full_name,
                            "file_path": rel_path,
                            "language": self._ext_to_language(ext),
                            "chunk_index": i,
                            "start_line": chunk.get("start_line", 0),
                            "end_line": chunk.get("end_line", 0),
                        })
                        ids.append(doc_id)
                        chunk_count += 1

                except Exception as e:
                    logger.debug(f"Dosya okuma hatası ({rel_path}): {e}")
                    continue

        if documents:
            # ChromaDB batch ekleme (max 5000 per batch)
            batch_size = 5000
            for i in range(0, len(documents), batch_size):
                batch_end = min(i + batch_size, len(documents))
                try:
                    self.collection.upsert(
                        documents=documents[i:batch_end],
                        metadatas=metadatas[i:batch_end],
                        ids=ids[i:batch_end],
                    )
                except Exception as e:
                    logger.error(f"ChromaDB batch ekleme hatası: {e}")

            logger.success(f"RAG: {chunk_count} chunk indekslendi ({repo_full_name})")

        return chunk_count

    def _chunk_file(self, content: str, ext: str, file_path: str) -> list[dict]:
        """Dosya içeriğini akıllı chunk'lara böler."""
        lines = content.split("\n")

        # Kod dosyaları: ~80 satırlık pencereler, 20 satır overlap
        if ext in {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp"}:
            return self._chunk_by_lines(lines, window=80, overlap=20)

        # Markdown/docs: paragraf bazlı
        if ext in {".md", ".txt", ".rst"}:
            return self._chunk_by_lines(lines, window=100, overlap=10)

        # Config/küçük dosyalar: tek chunk
        return [{"text": content, "start_line": 1, "end_line": len(lines)}]

    def _chunk_by_lines(self, lines: list[str], window: int = 80, overlap: int = 20) -> list[dict]:
        """Satır bazlı sliding window chunking."""
        chunks = []
        total = len(lines)

        if total <= window:
            return [{"text": "\n".join(lines), "start_line": 1, "end_line": total}]

        step = window - overlap
        for start in range(0, total, step):
            end = min(start + window, total)
            chunk_text = "\n".join(lines[start:end])
            if chunk_text.strip():
                chunks.append({
                    "text": chunk_text,
                    "start_line": start + 1,
                    "end_line": end,
                })
            if end >= total:
                break

        return chunks

    @staticmethod
    def _ext_to_language(ext: str) -> str:
        mapping = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "tsx", ".go": "go", ".rs": "rust",
            ".java": "java", ".c": "c", ".cpp": "cpp",
            ".rb": "ruby", ".php": "php",
            ".md": "markdown", ".yml": "yaml", ".yaml": "yaml",
            ".json": "json", ".toml": "toml",
            ".sh": "shell", ".bash": "shell",
        }
        return mapping.get(ext, "unknown")

    # ══════════════════════════════════════════════════════════
    #  SORGU - Issue/Discussion bağlamında relevant kod bul
    # ══════════════════════════════════════════════════════════

    def query_relevant_code(
        self,
        query_text: str,
        repo_full_name: str = None,
        n_results: int = 5,
    ) -> list[dict]:
        """
        Issue/Discussion metnine göre en alakalı kod parçalarını bulur.
        Returns: [{"text": "...", "file_path": "...", "language": "...", ...}, ...]
        """
        if not self.client or not self.collection:
            return []

        try:
            where_filter = {"repo": repo_full_name} if repo_full_name else None

            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            output = []
            for doc, meta, dist in zip(docs, metas, distances):
                output.append({
                    "text": doc,
                    "file_path": meta.get("file_path", ""),
                    "language": meta.get("language", ""),
                    "start_line": meta.get("start_line", 0),
                    "end_line": meta.get("end_line", 0),
                    "similarity": round(1.0 - dist, 4),
                })

            return output

        except Exception as e:
            logger.error(f"RAG sorgu hatası: {e}")
            return []

    def get_file_content_from_clone(self, clone_path: str, file_path: str) -> Optional[str]:
        """Klonlanmış repo'dan belirli bir dosyanın içeriğini okur."""
        full_path = os.path.join(clone_path, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            logger.debug(f"Dosya okunamadı ({file_path}): {e}")
            return None

    def delete_repo_index(self, repo_full_name: str):
        """Bir reponun tüm indeksini siler."""
        if not self.client or not self.collection:
            return
        try:
            # ChromaDB'de where filtresi ile silme
            self.collection.delete(where={"repo": repo_full_name})
            logger.info(f"RAG: {repo_full_name} indeksi silindi")
        except Exception as e:
            logger.error(f"RAG indeks silme hatası: {e}")
