from __future__ import annotations

import asyncio
import time
from typing import Optional

# ВАЖНО:
# - состояние хранится в памяти процесса (если у тебя несколько процессов/воркеров,
#   у каждого будет своё состояние)
# - lock создаём лениво, чтобы избежать привязки к неправильному event loop

_kb_ready: bool = False
_kb_last_load_ts: Optional[int] = None
_kb_loading_lock: Optional[asyncio.Lock] = None


def kb_is_ready() -> bool:
    return _kb_ready


def kb_mark_ready(value: bool) -> None:
    global _kb_ready
    _kb_ready = bool(value)


def kb_get_last_load_ts() -> Optional[int]:
    return _kb_last_load_ts


def kb_set_last_load_ts(ts: int | None = None) -> None:
    global _kb_last_load_ts
    if ts is None:
        ts = int(time.time())
    _kb_last_load_ts = int(ts)


def get_kb_loading_lock() -> asyncio.Lock:
    """
    Возвращает asyncio.Lock, создавая его лениво.
    Это избавляет от типовой проблемы: lock "привязан" к другому event loop.
    """
    global _kb_loading_lock
    if _kb_loading_lock is None:
        _kb_loading_lock = asyncio.Lock()
    return _kb_loading_lock
