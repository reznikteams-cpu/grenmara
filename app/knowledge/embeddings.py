from __future__ import annotations
from openai import OpenAI

def embed_texts(api_key: str, model: str, texts: list[str]) -> list[list[float]]:
    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]

def embed_query(api_key: str, model: str, text: str) -> list[float]:
    return embed_texts(api_key, model, [text])[0]
