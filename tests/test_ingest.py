import asyncio
from types import SimpleNamespace

import pytest

from app.knowledge.ingest import KnowledgeIngestor
from app.storage.db import Database
from app.storage.repo import Repo
from app.storage.schema import ensure_schema


def test_ensure_docs_loaded_skips_cached_document(monkeypatch, tmp_path):
    db_path = tmp_path / "bot.sqlite"
    db = Database(f"sqlite:///{db_path}")
    ensure_schema(db)

    repo = Repo(db)
    repo.upsert_document(source_key="gdocs:doc1:txt", title="Doc 1", raw_text="cached text")

    settings = SimpleNamespace(gdocs_sources=[{"doc_id": "doc1", "title": "Doc 1", "format": "txt"}])
    ingestor = KnowledgeIngestor(db=db, settings=settings)

    def _fail_export(*args, **kwargs):
        raise AssertionError("export_doc_text should not be called")

    monkeypatch.setattr("app.knowledge.ingest.export_doc_text", _fail_export)

    loaded = asyncio.run(ingestor.ensure_docs_loaded())

    assert loaded == 0
    assert repo.get_document_raw_text_by_source_key("gdocs:doc1:txt") == "cached text"
