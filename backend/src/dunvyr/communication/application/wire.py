"""JSON-safe wire representation of communication stream events."""

from __future__ import annotations

import json

from dunvyr.communication.domain.events import (
    ChatEvent,
    CheckResolvedEvent,
    GameSessionChangedEvent,
    MemberJoinedEvent,
    QueueChangedEvent,
)


def event_to_wire(event: ChatEvent) -> dict[str, object]:
    """Serialize one domain event into the stable WebSocket/REST envelope."""
    common: dict[str, object] = {
        "event_id": str(event.event_id),
        "campaign_id": str(event.campaign_id),
        "sequence": event.sequence,
        "occurred_at": event.occurred_at.isoformat(),
    }
    if isinstance(event, CheckResolvedEvent):
        return {"type": "check_resolved", **common, "result": json.loads(event.result_json)}
    if isinstance(event, QueueChangedEvent):
        return {"type": "queue_changed", **common, "queue_state": json.loads(event.state_json)}
    if isinstance(event, GameSessionChangedEvent):
        return {
            "type": "game_session_changed",
            **common,
            "game_session_state": {
                "revision": event.revision,
                "session": {
                    "id": str(event.session_id),
                    "status": event.status,
                    "started_at": event.started_at.isoformat(),
                    "ended_at": event.ended_at.isoformat() if event.ended_at else None,
                },
            },
        }
    if isinstance(event, MemberJoinedEvent):
        return {
            "type": "member_joined",
            **common,
            "member": {
                "guest_id": str(event.member.guest_id),
                "nickname": event.member.nickname,
                "role": event.member.role,
                "joined_at": event.member.joined_at.isoformat(),
            },
        }
    return {
        "type": "message",
        **common,
        "message": {
            "id": str(event.message.id),
            "author_id": str(event.message.author_id),
            "author_nickname": event.message.author_nickname,
            "client_message_id": str(event.message.client_message_id),
            "content": event.message.content,
            "created_at": event.message.created_at.isoformat(),
        },
    }


__all__ = ["event_to_wire"]
