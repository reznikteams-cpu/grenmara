from __future__ import annotations
import asyncio
import logging

from app.config import get_settings
from app.logging_setup import setup_logging
from app.storage.db import Database
from app.storage.schema import ensure_schema
from app.knowledge.ingest import KnowledgeIngestor
from app.bot.telegram_bot import build_application
from app.push.scheduler import SchedulerService

log = logging.getLogger(__name__)

async def _startup_kb(db: Database, settings):
    ingestor = KnowledgeIngestor(db=db, settings=settings)
    await ingestor.ensure_indexed_once()

async def main():
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info("Starting bot...")

    db = Database(settings.database_url)
    ensure_schema(db)

    # KB warm start (one-time)
    try:
        await _startup_kb(db, settings)
    except Exception as e:
    log.exception("KB startup failed, continuing without KB: %s", e)


    # Scheduler
    scheduler = SchedulerService(db=db, settings=settings)
    scheduler.start()

    # Telegram
    app = build_application(db=db, settings=settings, scheduler=scheduler)
    await app.initialize()
    await app.start()
    log.info("Bot started. Listening...")
    await app.updater.start_polling(drop_pending_updates=True)

    # keep alive
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
