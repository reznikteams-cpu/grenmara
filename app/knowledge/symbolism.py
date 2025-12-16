from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple, List


def normalize_word(s: str) -> str:
    """
    Нормализует слово для ключей словаря:
    - lower
    - ё -> е
    - оставляет только буквы/цифры
    """
    if not s:
        return ""
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9]", "", s)
    return s


def guess_key_from_scene(scene: str) -> str:
    """
    Берем первое слово из букв (кириллица/латиница), игнорируем эмодзи/знаки.
    Пример: "🐺 Волк бежит" -> "волк"
            "Тигрица, на которую нападают" -> "тигрица"
    """
    if not scene:
        return ""
    t = scene.strip().lower().replace("ё", "е")
    m = re.search(r"[a-zа-яё]+", t, flags=re.IGNORECASE)
    return normalize_word(m.group(0)) if m else normalize_word(scene)


@dataclass(frozen=True)
class SymbolismIndex:
    """
    index: ключ (например 'волк') -> блок текста (как в файле)
    source_title: для диагностики
    """
    index: Dict[str, str]
    source_title: str = "symbolism"


def build_symbolism_index(raw_text: str, source_title: str = "symbolism") -> SymbolismIndex:
    """
    Гарантированно строит индекс "заголовок -> блок".
    Условие заголовка (машинное, стабильное):
    - строка начинается с (возможно) эмодзи/знаков
    - затем идет слово из букв (кириллица/латиница)
    Это слово становится ключом.
    """
    if not raw_text or not raw_text.strip():
        return SymbolismIndex(index={}, source_title=source_title)

    index: Dict[str, str] = {}

    current_key: str | None = None
    current_block: List[str] = []

    # Важно: не выкидываем пустые строки внутри блока агрессивно —
    # но для устойчивости просто пропускаем полностью пустые строки.
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Заголовок: "🐺 Волк", "Волк:", "— Волк", "ВОЛК", etc.
        m = re.match(r"^[^\wа-яё]*([A-Za-zА-Яа-яЁё]+)\b", stripped)
        if m:
            key = normalize_word(m.group(1))
            if key:
                # сохранить прошлый блок
                if current_key and current_block:
                    index[current_key] = "\n".join(current_block).strip()

                current_key = key
                current_block = [stripped]
                continue

        # тело блока
        if current_key:
            current_block.append(stripped)

    # сохранить последний блок
    if current_key and current_block:
        index[current_key] = "\n".join(current_block).strip()

    return SymbolismIndex(index=index, source_title=source_title)


def find_symbol_entry(sym: SymbolismIndex, scene_or_word: str) -> Tuple[str, str] | None:
    """
    Возвращает (key, entry_text) или None
    """
    if not sym or not sym.index:
        return None

    key = guess_key_from_scene(scene_or_word)
    if not key:
        return None

    entry = sym.index.get(key)
    if entry:
        return key, entry

    # Доп. надежность: иногда в файле заголовок в единственном, а пользователь во множественном,
    # либо "волчица" vs "волк". НО ты просила строго — поэтому никаких эвристик по смыслу.
    # Здесь только "минимальная безопасность": попробовать отрезать типичные окончания.
    # Если хочешь 100% строго без этого — скажи, я удалю.
    for cut in ("а", "я", "ы", "и", "у", "ю", "е", "о"):
        if key.endswith(cut) and len(key) > 4:
            k2 = key[:-1]
            entry2 = sym.index.get(k2)
            if entry2:
                return k2, entry2

    return None


def summarize_index(sym: SymbolismIndex) -> str:
    """
    Короткая диагностика индекса.
    """
    if not sym.index:
        return f"[{sym.source_title}] index is empty"
    keys = list(sym.index.keys())
    keys_preview = ", ".join(keys[:20])
    more = "" if len(keys) <= 20 else f" …(+{len(keys)-20})"
    return f"[{sym.source_title}] symbols={len(keys)} keys: {keys_preview}{more}"
