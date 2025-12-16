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
    """
    Безопасный парсер булевых env-флагов.
    Важно: "0" -> False, "1" -> True.
    """
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


async def _startup_kb(db: Database, settings) -> None:
    """
    Прогреваем/индексируем KB на старте.
    ВАЖНО: после успешной прогрузки синхронизируем readiness-флаг в app.kb.state,
    чтобы остальная система не считала KB "не готовой".
    """
    t0 = time.time()
    ingestor = KnowledgeIngestor(db=db, settings=settings)
    await ingestor.ensure_indexed_once()

    # Синхронизация состояния KB (если модуль есть — он у тебя точно есть, т.к. lazy_loader его импортирует)
    try:
        from app.kb.state import kb_mark_ready, kb_set_last_load_ts  # локальный импорт: избежать циклов импорта

        kb_mark_ready(True)
        kb_set_last_load_ts(int(time.time()))
    except Exception as e:
        # Даже если readiness не смогли отметить — лучше продолжать, но явно залогировать,
        # иначе потом будут "магические" lazy-load'ы и ощущение что KB не грузится.
        log.warning("KB warm start done, but failed to mark KB ready in app.kb.state: %s", e)

    log.info("KB warm start success in %.2fs", time.time() - t0)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    log.info("Starting bot...")

    db = Database(settings.database_url)
    ensure_schema(db)

    # KB warm start (не роняем весь бот, но делаем поведение предсказуемым)
    kb_disable_startup = _env_flag("KB_DISABLE_STARTUP", default=False)
    log.info("KB_DISABLE_STARTUP=%r (parsed=%s)", os.getenv("KB_DISABLE_STARTUP"), kb_disable_startup)

    if kb_disable_startup:
        log.warning("KB startup disabled by env KB_DISABLE_STARTUP")
        # Если отключили стартап — явно отмечаем "не готово", чтобы логика была консистентной
        try:
            from app.kb.state import kb_mark_ready  # локальный импорт

            kb_mark_ready(False)
        except Exception:
            pass
    else:
        try:
            await _startup_kb(db, settings)
        except Exception as e:
            # Важно: если стартап не удался — отмечаем неготовность, чтобы не было "полу-состояния"
            try:
                from app.kb.state import kb_mark_ready  # локальный импорт

                kb_mark_ready(False)
            except Exception:
                pass
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

