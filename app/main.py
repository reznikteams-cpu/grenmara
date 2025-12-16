from __future__ import annotations

import asyncio
import logging
import os

from app.config import get_settings
from app.logging_setup import setup_logging
from app.storage.db import Database
from app.storage.schema import ensure_schema
from app.knowledge.ingest import KnowledgeIngestor
from app.bot.telegram_bot import build_application
from app.push.scheduler import SchedulerService

log = logging.getLogger(__name__)


async def _startup_kb(db: Database, settings) -> None:
    ingestor = KnowledgeIngestor(db=db, settings=settings)
    await ingestor.ensure_indexed_once()


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info("Starting bot...")

    db = Database(settings.database_url)
    ensure_schema(db)

    # KB warm start (do not crash whole app if fails)
    if os.getenv("KB_DISABLE_STARTUP") == "1":
        log.warning("KB startup disabled by env KB_DISABLE_STARTUP=1")
    else:
        try:
            await _startup_kb(db, settings)
        except Exception as e:
            log.exception("KB startup failed, continuing without KB: %s", e)

    scheduler = SchedulerService(db=db, settings=settings)
    scheduler.start()

    application = build_application(db=db, settings=settings, scheduler=scheduler)
    await application.initialize()
    await application.start()

    log.info("Bot started. Listening...")
    await application.updater.start_polling(drop_pending_updates=True)

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
