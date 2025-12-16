from __future__ import annotations

import logging
import httpx

log = logging.getLogger(__name__)


def export_doc_text(doc_id: str, fmt: str = "txt") -> str:
    url = f"https://docs.google.com/document/d/{doc_id}/export?format={fmt}"
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            r = client.get(url)

        log.info(
            "GDOCS export response: doc_id=%s status=%s len=%s url=%s",
            doc_id,
            r.status_code,
            len(r.text or ""),
            url,
        )

        if r.status_code != 200:
            preview = (r.text or "")[:800]
            log.error("GDOCS export failed: status=%s url=%s preview=%r", r.status_code, url, preview)
            r.raise_for_status()

        text = r.text or ""
        low = text.lower()

        # Если вместо текста пришла HTML-страница (логин/ошибка) — это невалидно для RAG
        if "<html" in low or "accounts.google.com" in low:
            log.error(
                "GDOCS export returned HTML (likely private/blocked). url=%s preview=%r",
                url,
                text[:800],
            )
            raise RuntimeError("GDOCS export returned HTML (doc likely not accessible via export).")

        if not text.strip():
            log.error("GDOCS export returned empty text. url=%s", url)
            raise RuntimeError("GDOCS export returned empty text.")

        return text

    except Exception:
        log.exception("GDOCS export exception for doc_id=%s url=%s", doc_id, url)
        raise
