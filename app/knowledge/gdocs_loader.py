from __future__ import annotations
import httpx

def export_doc_text(doc_id: str, fmt: str = "txt") -> str:
    # Works if doc is shareable via link (public or anyone-with-link)
    # Formats: txt, docx, pdf, html (txt easiest)
    url = f"https://docs.google.com/document/d/{doc_id}/export?format={fmt}"
    with httpx.Client(timeout=30) as client:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        if fmt == "txt":
            return r.text
        # keep simple: for non-txt user should parse separately
        return r.text
