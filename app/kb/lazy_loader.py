import os
import time
import logging
import asyncio

from app.kb.state import kb_is_ready, kb_mark_ready, kb_set_last_load_ts

log = logging.getLogger(__name__)


class KBLoadError(RuntimeError):
    pass


def _env_flag(name: str, default: bool = False) -> bool:
    """
    Нормальный парсер булевых env-флагов.
    Важно: строка "0" должна быть False, иначе будет вечная путаница.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip().lower()
    if raw in ("1", "true", "yes", "y", "on"):
        return True
    if raw in ("0", "false", "no", "n", "off", ""):
        return False
    # Если прилетело что-то странное — считаем True, но явно логируем.
    log.warning("Env %s has unexpected value %r; treating as True", name, raw)
    return True


def _get_lock() -> asyncio.Lock:
    """
    Создаём lock лениво, чтобы не привязать его к "не тому" event loop.
    """
    lock = getattr(_get_lock, "_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(_get_lock, "_lock", lock)
    return lock


async def ensure_kb_loaded(load_fn):
    """
    load_fn: async function, которая реально грузит/парсит KB (твой существующий код).
    """
    if kb_is_ready():
        return True

    lock = _get_lock()
    async with lock:
        if kb_is_ready():
            return True

        disable_startup = _env_flag("KB_DISABLE_STARTUP", default=False)
        log.warning(
            "KB not ready -> lazy loading triggered (KB_DISABLE_STARTUP=%s)",
            disable_startup,
        )

        try:
            t0 = time.time()
            await load_fn()  # здесь твой реальный импорт/парсинг "Символизм"
            kb_mark_ready(True)
            kb_set_last_load_ts(int(time.time()))
            log.info("KB lazy load success in %.2fs", time.time() - t0)
            return True
        except Exception as e:
            kb_mark_ready(False)
            log.exception("KB lazy load failed: %s", e)
            raise KBLoadError(str(e)) from e
