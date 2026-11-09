"""LLM invocation, result description, NPC speech, semantic matching and prompt contracts."""

from __future__ import annotations

import json
from typing import Any


def context_payload(success: bool, facts: tuple[str, ...]) -> dict[str, Any]:
    if (
        type(success) is not bool
        or len(facts) > 8
        or any(not isinstance(fact, str) or len(fact) > 512 for fact in facts)
    ):
        raise ValueError("invalid narration context")
    payload = {
        "success": success,
        "facts": [{"ref": f"f{i}", "text": fact} for i, fact in enumerate(facts, 1)],
    }
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 8192:
        raise ValueError("narration context limit exceeded")
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response key")
        result[key] = value
    return result


def render_response(response: bytes, success: bool, facts: tuple[str, ...]) -> str:
    """Render only server-owned facts; provider output cannot introduce prose."""
    context_payload(success, facts)
    if len(response) > 32768:
        raise ValueError("narration limit exceeded")
    try:
        data = json.loads(response.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid narration response") from exc
    opening = "success" if success else "failure"
    refs = [f"f{i}" for i in range(1, len(facts) + 1)]
    if (
        not isinstance(data, dict)
        or set(data) != {"opening", "fact_refs"}
        or data["opening"] != opening
        or data["fact_refs"] != refs
    ):
        raise ValueError("invalid narration response")
    text = " ".join(("Действие удалось." if success else "Действие не удалось.", *facts))
    if len(text) > 4500:
        raise ValueError("narration limit exceeded")
    return text
