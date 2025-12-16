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


def _set_kb_state(ready: bool) -> None:
    """
    Синхронизация in-memory состояния KB.
    Не должна ронять приложение.
    """
    try:
        from app.kb.state import kb_mark_ready, kb_set_last_load_ts

        kb_mark_ready(bool(ready))
        if ready:
            kb_set_last_load_ts(int(time.time()))
    except Exception:
        log.exception("Failed to update app.kb.state (ready=%s)", ready)


async def _startup_kb(db: Database, settings) -> int:
    """
    Прогреваем/индексируем KB на старте.
    Возвращает количество чанков, записанных в БД в рамках этого запуска (0 если чанки уже были).
    """
    t0 = time.time()
    ingestor = KnowledgeIngestor(db=db, settings=settings)
    indexed = await ingestor.ensure_indexed_once()
    log.info("KB warm start finished in %.2fs (indexed=%s)", time.time() - t0, indexed)
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

    # KB warm start (не роняем весь бот, но делаем состояние предсказуемым)
    if kb_disable_startup:
        log.warning("KB startup disabled by env KB_DISABLE_STARTUP")
        _set_kb_state(False)
    else:
        try:
            indexed = await _startup_kb(db, settings)

            # Если в БД уже были чанки — indexed=0, но это не значит, что KB "не готова".
            # Готовность здесь = возможность работать с KB (документы/чанки присутствуют).
            # Поэтому: если старт прошёл без исключений — считаем ready=True.
            _set_kb_state(True)

            if indexed > 0:
                log.info("KB warmed successfully (new chunks=%s)", indexed)
            else:
                log.info("KB already present (no new chunks indexed)")
       except Exception as e:
    try:
        from app.kb.state import kb_mark_ready
        kb_mark_ready(False)
    except Exception:
        pass

    log.exception("KB reload failed: %s", e)
    await update.effective_message.reply_text(
        "Ошибка при обновлении KB ❌\nСмотри логи сервера."
    )

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
