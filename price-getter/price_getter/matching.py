"""Product matching for the basket problem, inverted:

- embeddings turn a shopping-list item into a vector for nearest-product lookup
  (pgvector kNN happens on the database; this module produces the vectors)
- the LLM settles close calls between the top candidates

sentence-transformers is an optional extra (`uv sync --extra matching`); it is
imported lazily so the base install and CI stay torch-free.
"""

from __future__ import annotations

import json

from openai import OpenAI

from price_getter.config import get_settings

_model: object | None = None
_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384-d, matches schema.sql


class EmbeddingModelUnavailable(RuntimeError):
    """sentence-transformers extra is not installed."""


def encode_texts(texts: list[str]) -> list[list[float]]:
    """Embed item names with MiniLM; must be applied to both list items and
    store products before similarity is meaningful.
    """
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingModelUnavailable(
                "Embeddings need the matching extra: cd price-getter && uv sync --extra matching"
            ) from exc
        _model = SentenceTransformer(_MODEL_NAME)
    return _model.encode(  # type: ignore[attr-defined]
        texts, normalize_embeddings=True
    ).tolist()


def llm_settle(item_name: str, candidates: list[dict]) -> dict | None:
    """Ask an LLM to pick which candidate product really matches the item.

    `candidates` come from the kNN shortlist: dicts like
    `{"name": ..., "size": ..., "price_per_100g": ...}`.
    Returns the chosen candidate or None when nothing matches (e.g. the list
    contains an item the store doesn't stock).
    """
    settings = get_settings()
    client = OpenAI(
        api_key=settings.openai_api_key or None,
        base_url=settings.llm_base_url or None,  # non-OpenAI providers
    )
    prompt = (
        "Shopping list item: "
        f'"{item_name}"\n'
        "Candidates:\n"
        + "\n".join(f"- {c!r}" for c in candidates)
        + "\nWhich candidate is the same grocery item? "
        'Reply with JSON: {"match": <index> | null}. Only same-product matches count.'
    )
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )

    answer = json.loads(resp.choices[0].message.content or "{}")
    idx = answer.get("match")
    return candidates[idx] if isinstance(idx, int) and 0 <= idx < len(candidates) else None
