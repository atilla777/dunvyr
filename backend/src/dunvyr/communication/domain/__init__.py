"""Communication domain layer: messages, chat stream events and invariants."""


def can_retry_narration(state: str, revision: int, expected: int, elapsed: float) -> bool:
    return state == "failed" and revision == expected and elapsed >= 10


def can_complete_narration(
    state: str, revision: int, token: str | None, expected_revision: int, expected_token: str
) -> bool:
    """An earlier attempt cannot publish over a newer claim or a terminal result."""
    return (
        state == "generating"
        and revision == expected_revision
        and token is not None
        and token == expected_token
    )
