from __future__ import annotations

import logging
from typing import Iterable

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
        Старое поведение: если нет chunks — индексируем.
        Возвращает количество новых чанков (примерно).
        """
        # Всегда гарантируем, что raw_text загружен — без этого бот не сможет отвечать
        # даже если эмбеддинги недоступны.
        loaded_raw = await self.ensure_docs_loaded()

        # Если нет ключа — ограничиваемся только загрузкой raw_text (без reindex_all())
        if not self.settings.openai_api_key:
            log.warning(
                "OPENAI_API_KEY is missing -> skipping embeddings/chunk indexing. raw_text loaded=%s",
                loaded_raw,
            )
            return loaded_raw

        rows = self.db.query("SELECT COUNT(*) AS c FROM kb_chunks")
        if int(rows[0]["c"]) > 0:
            return 0
        return await self.reindex_all()

    async def ensure_docs_loaded(self, titles: Iterable[str] | None = None) -> int:
        """
        НОВОЕ: гарантированно загружает raw_text документов в kb_documents (без эмбеддингов).
        Это нужно, чтобы бот мог читать "Символизм" даже при KB_DISABLE_STARTUP=1 или без OPENAI_API_KEY.
        Возвращает количество загруженных документов.
        """
        if not self.settings.gdocs_sources:
            log.warning("No GDOCS_SOURCES configured. KB will be empty.")
            return 0

        wanted = None
        if titles:
            wanted = {t.strip().lower() for t in titles if t and t.strip()}

        loaded = 0
        for src in self.settings.gdocs_sources:
            doc_id = src["doc_id"]
            title = (src.get("title") or doc_id).strip()
            fmt = src.get("format", "txt")
            source_key = f"gdocs:{doc_id}:{fmt}"

            if wanted and title.strip().lower() not in wanted:
                continue

            existing_raw = self.repo.get_document_raw_text_by_source_key(source_key)
            if existing_raw and existing_raw.strip():
                log.info("Document %s already loaded, skipping download", title)
                continue

            log.info("Loading doc %s (%s)...", title, doc_id)
            raw = export_doc_text(doc_id=doc_id, fmt=fmt)

            # ВАЖНО: raw_text сохраняем всегда
            self.repo.upsert_document(source_key=source_key, title=title, raw_text=raw)
            loaded += 1

        return loaded

    async def reindex_all(self) -> int:
        """
        Индексирует всё: raw_text + chunks + embeddings (если есть OPENAI_API_KEY).
        Если OPENAI_API_KEY нет — просто загрузит raw_text в kb_documents и завершит без падения.
        """
        # Сначала гарантируем raw_text
        loaded = await self.ensure_docs_loaded()

        # Если нет ключа — НЕ падаем. Для "Символизма" нам достаточно raw_text.
        if not self.settings.openai_api_key:
            log.warning("OPENAI_API_KEY is missing -> skipping embeddings/chunk indexing. raw_text loaded=%s", loaded)
            return 0

        total_chunks = 0
        for src in self.settings.gdocs_sources:
            doc_id = src["doc_id"]
            title = (src.get("title") or doc_id).strip()
            fmt = src.get("format", "txt")
            source_key = f"gdocs:{doc_id}:{fmt}"

            raw = export_doc_text(doc_id=doc_id, fmt=fmt)
            doc_db_id = self.repo.upsert_document(source_key=source_key, title=title, raw_text=raw)

            chunks = chunk_text(raw, chunk_size=1400, overlap=180)
            if not chunks:
                log.warning("Doc %s has no chunks after chunking.", title)
                continue

            log.info("Embedding %d chunks for %s...", len(chunks), title)
            embs = embed_texts(
                api_key=self.settings.openai_api_key,
                model=self.settings.embedding_model,
                texts=chunks,
            )

            packed = [(i, chunks[i], embs[i]) for i in range(len(chunks))]
            self.repo.replace_chunks(doc_id=doc_db_id, chunks=packed)

            total_chunks += len(chunks)
            log.info("Indexed %s: %d chunks", title, len(chunks))

        return total_chunks
