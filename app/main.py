from __future__ import annotations

import asyncio
import logging
import os
import time

from app.config import get_settings
from app.logging_setup import setup_logging
from app.storage.db import Database
from app.storage.schema import ensure_schema
from app.knowledge.ingest import KnowledgeIngestor
from app.bot.telegram_bot import build_application
from app.push.scheduler import SchedulerService

log = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    raw = raw.strip().lower()
    if raw in ("1", "true", "yes", "y", "on"):
        return True
    if raw in ("0", "false", "no", "n", "off", ""):
        return False

    log.warning("Env %s has unexpected value %r; treating as True", name, raw)
    return True


def _set_kb_state(ready: bool) -> None:
    try:
        from app.kb.state import kb_mark_ready, kb_set_last_load_ts

        kb_mark_ready(bool(ready))
        if ready:
            kb_set_last_load_ts(int(time.time()))
    except Exception:
        log.exception("Failed to update KB state")


async def _startup_kb(db: Database, settings) -> int:
    start_ts = time.time()
    ingestor = KnowledgeIngestor(db=db, settings=settings)
    indexed = await ingestor.ensure_indexed_once()
    log.info(
        "KB warm start finished in %.2fs (indexed=%s)",
        time.time() - start_ts,
        indexed,
    )
    return int(indexed or 0)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    log.info("Starting bot...")

    db = Database(settings.database_url)
    ensure_schema(db)

    kb_disable_startup = _env_flag("KB_DISABLE_STARTUP", default=False)
    log.info(
        "KB_DISABLE_STARTUP=%r (parsed=%s)",
        os.getenv("KB_DISABLE_STARTUP"),
        kb_disable_startup,
    )

    if kb_disable_startup:
        log.warning("KB startup disabled by env KB_DISABLE_STARTUP")
        _set_kb_state(False)
    else:
        try:
            indexed = await _startup_kb(db, settings)
            _set_kb_state(True)

            if indexed > 0:
                log.info("KB warmed successfully (new chunks=%s)", indexed)
            else:
                log.info("KB already present (no new chunks indexed)")

        except Exception as e:
            _set_kb_state(False)
            log.exception("KB startup failed, continuing without KB: %s", e)

    # === дальше у тебя этого НЕ БЫЛО ===

    scheduler = SchedulerService(db=db, settings=settings)
    scheduler.start()

    application = build_application(
        db=db,
        settings=settings,
        scheduler=scheduler,
    )

    await application.initialize()
    await application.start()

    log.info("Bot started. Listening...")
    await application.updater.start_polling(drop_pending_updates=True)

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
