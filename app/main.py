from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import traceback
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger(__name__)

try:
    from app.config import get_settings
    from app.logging_setup import setup_logging
    from app.storage.db import Database
    from app.storage.schema import ensure_schema
    from app.knowledge.ingest import KnowledgeIngestor
    from app.bot.telegram_bot import build_application
    from app.push.scheduler import SchedulerService
except Exception as e:
    print("FATAL: import failed in app.main.py:", repr(e), flush=True)
    traceback.print_exc()
    raise


def _start_health_server() -> None:
    """
    Railway Web Service часто ждёт, что процесс слушает $PORT.
    Этот мини-сервер отвечает 200 OK и предотвращает рестарты.
    """
    port = int(os.getenv("PORT", "8080"))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, format, *args):
            return  # не спамим логи

    server = HTTPServer(("0.0.0.0", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("Health server listening on 0.0.0.0:%s", port)


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
    ingestor = KnowledgeIngestor(db=db, settings=settings)
    indexed = await ingestor.ensure_indexed_once()
    return int(indexed or 0)


async def main() -> None:
    print("MAIN: entered main()", flush=True)

    settings = get_settings()
    setup_logging(settings.log_level)

    # <<< ключевой фикс для Railway Web >>>
    _start_health_server()

    log.info("Starting bot...")

    db = Database(settings.database_url)
    ensure_schema(db)

    kb_disable_startup = _env_flag("KB_DISABLE_STARTUP", default=False)
    log.info("KB_DISABLE_STARTUP=%r (parsed=%s)", os.getenv("KB_DISABLE_STARTUP"), kb_disable_startup)

    if kb_disable_startup:
        log.warning("KB startup disabled by env KB_DISABLE_STARTUP")
        _set_kb_state(False)
    else:
        try:
            indexed = await _startup_kb(db, settings)
            _set_kb_state(True)
            log.info("KB warm start done (indexed=%s)", indexed)
        except Exception as e:
            _set_kb_state(False)
            log.exception("KB startup failed, continuing without KB: %s", e)

    scheduler = SchedulerService(db=db, settings=settings)
    scheduler.start()

    application = build_application(db=db, settings=settings, scheduler=scheduler)
    await application.initialize()
    await application.start()

    try:
    await application.bot.delete_webhook(drop_pending_updates=True)
    except Exception:
    log.exception("delete_webhook failed")

    
    log.info("Bot started. Listening...")
    await application.updater.start_polling(drop_pending_updates=True)

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        print("MAIN: __main__ reached, starting asyncio.run(main())", flush=True)
        asyncio.run(main())
    except Exception as e:
        print("FATAL: app crashed:", repr(e), flush=True)
        traceback.print_exc()
        sys.exit(1)
