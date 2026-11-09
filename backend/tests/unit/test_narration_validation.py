import pytest

import dunvyr.narration as narration

pytestmark = pytest.mark.unit


def test_response_can_only_select_ordered_public_facts():
    render = getattr(narration, "render_response", lambda *_: None)
    assert (
        render(
            b'{"opening":"success","fact_refs":["f1","f2"]}',
            True,
            ("Дверь открыта.", "Путь свободен."),
        )
        == "Действие удалось. Дверь открыта. Путь свободен."
    )


@pytest.mark.parametrize(
    "response",
    [
        b'{"opening":"success","fact_refs":["f2","f1"]}',
        b'{"opening":"success","fact_refs":["f1","f1"]}',
        b'{"opening":"success","fact_refs":["f1"]}',
        b'{"opening":"failure","fact_refs":["f1","f2"]}',
        b'{"opening":"success","fact_refs":["f1","f2"],"text":"secret"}',
        b'{"opening":"success","opening":"success","fact_refs":["f1","f2"]}',
        b'{"opening":"success","fact_refs":["f1","f2"]} trailing',
        b"\xff",
        b" " * 32769,
    ],
)
def test_untrusted_responses_are_rejected(response):
    render = getattr(narration, "render_response", lambda *_: None)
    with pytest.raises(ValueError):
        render(response, True, ("Один", "Два"))


def test_fact_snapshot_rejects_more_than_eight_kib_utf8():
    render = getattr(narration, "render_response", lambda *_: None)
    with pytest.raises(ValueError):
        render(
            b'{"opening":"success","fact_refs":["f1","f2","f3","f4","f5","f6","f7","f8"]}',
            True,
            ("界" * 512,) * 8,
        )


@pytest.mark.parametrize("success,facts", [(1, ()), (True, ("a" * 513,)), (True, ("a",) * 9)])
def test_context_is_validated_before_any_provider_call(success, facts):
    factory = getattr(narration, "context_payload", lambda *_: b"unchecked")
    with pytest.raises(ValueError):
        factory(success, facts)


def test_provider_context_has_only_success_and_ordered_local_fact_references():
    factory = getattr(narration, "context_payload", lambda *_: None)
    assert factory(True, ("Дверь открыта.",)) == {
        "success": True,
        "facts": [{"ref": "f1", "text": "Дверь открыта."}],
    }
