from __future__ import annotations
import numpy as np
from openai import OpenAI

def cosine_sim(a: list[float], b: list[float]) -> float:
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-9
    return float(np.dot(va, vb) / denom)

def top_k_chunks(query_emb: list[float], chunks: list[tuple[int, str, list[float]]], k: int) -> list[tuple[int, str, float]]:
    scored = []
    for chunk_id, content, emb in chunks:
        scored.append((chunk_id, content, cosine_sim(query_emb, emb)))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:k]

def build_context(chunks: list[tuple[int, str, float]], max_chars: int) -> str:
    parts = []
    total = 0
    for _, content, score in chunks:
        block = f"[score={score:.3f}]\n{content.strip()}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n---\n".join(parts)

def llm_answer(
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
) -> str:
    client = OpenAI(api_key=api_key)
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            *messages,
        ],
    )
    # normalize
    out = []
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    out.append(c.text)
    return "\n".join(out).strip()
