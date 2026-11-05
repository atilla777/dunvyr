"""TDD unit tests for the communication application services with fakes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from dunvyr.campaigns.public import CampaignMemberSnapshot
from dunvyr.communication.application.errors import (
    ClientMessageConflict,
    EventAppendConflict,
    NotAMember,
)
from dunvyr.communication.application.service import (
    ChatService,
    MemberEventService,
    SendMessage,
)
from dunvyr.communication.domain.events import ChatEvent, MemberJoinedEvent, MessageEvent

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CAMPAIGN_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_CAMPAIGN_ID = UUID("99999999-9999-4999-8999-999999999999")
ALICE_ID = UUID("11111111-1111-4111-8111-111111111111")
BOB_ID = UUID("33333333-3333-4333-8333-333333333333")
MESSAGE_ID = UUID("44444444-4444-4444-8444-444444444444")
EVENT_ID = UUID("55555555-5555-4555-8555-555555555555")
CLIENT_ID = UUID("66666666-6666-4666-8666-666666666666")


def member(guest_id: UUID, nickname: str, role: str = "player") -> CampaignMemberSnapshot:
    return CampaignMemberSnapshot(
        guest_id=guest_id,
        nickname=nickname,
        role=role,
        joined_at=NOW,
    )


class FakeEventRepository:
    def __init__(self) -> None:
        self.events: list[ChatEvent] = []
        self.sequence_override: list[int] = []
        self.append_conflicts: int = 0

    def find_message_by_client_id(
        self,
        campaign_id: UUID,
        client_message_id: UUID,
    ) -> MessageEvent | None:
        return next(
            (
                event
                for event in self.events
                if isinstance(event, MessageEvent)
                and event.campaign_id == campaign_id
                and event.message.client_message_id == client_message_id
            ),
            None,
        )

    def find_member_joined(
        self,
        campaign_id: UUID,
        guest_id: UUID,
    ) -> MemberJoinedEvent | None:
        return next(
            (
                event
                for event in self.events
                if isinstance(event, MemberJoinedEvent)
                and event.campaign_id == campaign_id
                and event.member.guest_id == guest_id
            ),
            None,
        )

    def next_sequence(self, campaign_id: UUID) -> int:
        if self.sequence_override:
            return self.sequence_override.pop(0)
        sequences = [event.sequence for event in self.events if event.campaign_id == campaign_id]
        return max(sequences, default=0) + 1

    def append(self, event: ChatEvent) -> None:
        if self.append_conflicts > 0:
            self.append_conflicts -= 1
            raise EventAppendConflict
        self.events.append(event)

    def list_events(
        self,
        campaign_id: UUID,
        *,
        after_sequence: int | None,
        limit: int,
    ) -> list[ChatEvent]:
        events = sorted(
            (event for event in self.events if event.campaign_id == campaign_id),
            key=lambda event: event.sequence,
        )
        if after_sequence is not None:
            events = [event for event in events if event.sequence > after_sequence]
        return events[:limit]

    def last_sequence(self, campaign_id: UUID) -> int:
        return max(
            (event.sequence for event in self.events if event.campaign_id == campaign_id),
            default=0,
        )


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.events = FakeEventRepository()
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FakeMembershipReader:
    def __init__(
        self, members: list[CampaignMemberSnapshot], campaign_id: UUID = CAMPAIGN_ID
    ) -> None:
        self.members = {member.guest_id: member for member in members}
        self.campaign_id = campaign_id

    def find_member(
        self,
        campaign_id: UUID,
        guest_id: UUID,
    ) -> CampaignMemberSnapshot | None:
        if campaign_id != self.campaign_id:
            return None
        return self.members.get(guest_id)

    def remove(self, guest_id: UUID) -> None:
        self.members.pop(guest_id, None)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FixedIdFactory:
    def __init__(self) -> None:
        self.calls = 0
        self.fixed: dict[int, UUID] = {}

    def __call__(self) -> UUID:
        self.calls += 1
        return self.fixed.get(self.calls, UUID(int=self.calls))


def build_chat_service(
    *,
    members: list[CampaignMemberSnapshot] | None = None,
    uow: FakeUnitOfWork | None = None,
) -> tuple[ChatService, FakeUnitOfWork, FakeMembershipReader]:
    resolved_uow = uow or FakeUnitOfWork()
    reader = FakeMembershipReader(members or [member(ALICE_ID, "Алиса", "organizer")])
    service = ChatService(
        unit_of_work=resolved_uow,
        membership_reader=reader,
        clock=FixedClock(NOW),
        id_factory=FixedIdFactory(),
    )
    return service, resolved_uow, reader


def send_command(**overrides: object) -> SendMessage:
    values: dict[str, object] = {
        "campaign_id": CAMPAIGN_ID,
        "author_id": ALICE_ID,
        "client_message_id": CLIENT_ID,
        "content": "Привет",
    }
    values.update(overrides)
    return SendMessage(**values)  # type: ignore[arg-type]


@pytest.mark.unit
def test_send_message_uses_the_server_membership_and_assigns_ordered_sequences() -> None:
    service, uow, _reader = build_chat_service()

    first = service.send_message(send_command())
    second = service.send_message(send_command(client_message_id=UUID(int=77), content="Ещё"))

    assert first.created is True
    assert first.event.message.author_id == ALICE_ID
    assert first.event.message.author_nickname == "Алиса"
    assert [first.event.sequence, second.event.sequence] == [1, 2]
    assert uow.commits == 2
    assert len(uow.events.events) == 2


@pytest.mark.unit
def test_send_message_rejects_a_non_member_before_any_write() -> None:
    service, uow, reader = build_chat_service()
    reader.remove(ALICE_ID)

    with pytest.raises(NotAMember):
        service.send_message(send_command())

    assert uow.commits == 0
    assert uow.events.events == []


@pytest.mark.unit
def test_replayed_client_message_id_returns_the_original_event_without_a_commit() -> None:
    service, uow, _reader = build_chat_service()

    first = service.send_message(send_command())
    replay = service.send_message(send_command())

    assert first.created is True
    assert replay.created is False
    assert replay.event.event_id == first.event.event_id
    assert uow.commits == 1
    assert len(uow.events.events) == 1


@pytest.mark.unit
def test_client_message_id_reuse_by_another_author_is_a_conflict() -> None:
    service, uow, _reader = build_chat_service(
        members=[member(ALICE_ID, "Алиса", "organizer"), member(BOB_ID, "Боб")]
    )
    service.send_message(send_command())

    with pytest.raises(ClientMessageConflict):
        service.send_message(send_command(author_id=BOB_ID))

    assert len(uow.events.events) == 1


@pytest.mark.unit
def test_sequence_conflict_is_retried_without_losing_the_message() -> None:
    service, uow, _reader = build_chat_service()
    uow.events.append_conflicts = 1

    result = service.send_message(send_command())

    assert result.created is True
    assert result.event.sequence == 1
    assert uow.commits == 1


@pytest.mark.unit
def test_history_requires_membership_and_returns_ordered_events_after_a_cursor() -> None:
    service, uow, _reader = build_chat_service()
    service.send_message(send_command())
    service.send_message(send_command(client_message_id=UUID(int=78), content="Второе"))

    with pytest.raises(NotAMember):
        service.get_history(CAMPAIGN_ID, BOB_ID)

    history = service.get_history(CAMPAIGN_ID, ALICE_ID, after_sequence=1)

    assert [event.sequence for event in history.events] == [2]
    assert history.last_sequence == 2
    assert uow.commits == 2


@pytest.mark.unit
def test_member_joined_events_are_persisted_once_with_their_own_sequence() -> None:
    uow = FakeUnitOfWork()
    service = MemberEventService(
        unit_of_work=uow,
        clock=FixedClock(NOW),
        id_factory=FixedIdFactory(),
    )
    chat, _chat_uow, _reader = build_chat_service(uow=uow)
    chat.send_message(send_command())
    bob = member(BOB_ID, "Боб")

    first = service.record_member_joined(CAMPAIGN_ID, bob)
    replay = service.record_member_joined(CAMPAIGN_ID, bob)

    assert first.created is True
    assert replay.created is False
    assert replay.event.event_id == first.event.event_id
    assert first.event.sequence == 2
    assert first.event.member.nickname == "Боб"
    assert uow.commits == 2
    assert len(uow.events.events) == 2
