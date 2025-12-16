from __future__ import annotations

import logging

from app.storage.db import Database
from app.storage.repo import Repo
from app.knowledge.gdocs_loader import export_doc_text
from app.knowledge.chunker import chunk_text
from app.knowledge.embeddings import embed_texts

log = logging.getLogger(__name__)


class KnowledgeIngestor:
    def __init__(self, db: Database, settings):
        self.db = db
        self.repo = Repo(db)
        self.settings = settings

    async def ensure_indexed_once(self) -> int:
        """
        Если в БД уже есть чанки — ничего не делаем.
        Возвращает число чанков, добавленных/переиндексированных в этом вызове (0 если не было работы).
        """
        rows = self.db.query("SELECT COUNT(*) AS c FROM kb_chunks")
        if int(rows[0]["c"]) > 0:
            return 0
        return await self.reindex_all()

    async def reindex_all(self) -> int:
        """
        Полная переиндексация KB из источников (Google Docs).
        Возвращает суммарное число чанков, записанных в БД.
        """
        if not self.settings.gdocs_sources:
            log.warning("No GDOCS_SOURCES configured. KB will be empty.")
            return 0

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for embeddings/RAG")

        total_chunks_written = 0

        for src in self.settings.gdocs_sources:
            doc_id = src["doc_id"]
            title = src.get("title", doc_id)
            fmt = src.get("format", "txt")
            source_key = f"gdocs:{doc_id}:{fmt}"

            log.info("Loading doc %s (%s)...", title, doc_id)
            raw = export_doc_text(doc_id=doc_id, fmt=fmt)

            doc_db_id = self.repo.upsert_document(source_key=source_key, title=title, raw_text=raw)

            chunks = chunk_text(raw, chunk_size=1400, overlap=180)
            if not chunks:
                log.warning("Doc %s has no chunks after chunking.", title)
                # Важно: документ всё равно сохранили сырьём, но чанков нет
                continue

            log.info("Embedding %d chunks for %s...", len(chunks), title)
            embs = embed_texts(
                api_key=self.settings.openai_api_key,
                model=self.settings.embedding_model,
                texts=chunks,
            )

            packed = [(i, chunks[i], embs[i]) for i in range(len(chunks))]
            self.repo.replace_chunks(doc_id=doc_db_id, chunks=packed)

            total_chunks_written += len(chunks)
            log.info("Indexed %s: %d chunks", title, len(chunks))

        log.info("KB reindex_all completed. Total chunks written: %d", total_chunks_written)
        return total_chunks_written
