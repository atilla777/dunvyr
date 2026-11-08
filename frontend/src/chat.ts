export interface ChatMember {
  guest_id: string;
  nickname: string;
  role: string;
  joined_at: string;
}

export interface ChatMessage {
  id: string;
  author_id: string;
  author_nickname: string;
  client_message_id: string;
  content: string;
  created_at: string;
}

interface ChatEventBase {
  event_id: string;
  campaign_id: string;
  sequence: number;
  occurred_at: string;
}

export interface ChatMessageEvent extends ChatEventBase {
  type: 'message';
  message: ChatMessage;
}

export interface ChatMemberJoinedEvent extends ChatEventBase {
  type: 'member_joined';
  member: ChatMember;
}

export interface GameSessionState {
  revision: number;
  session: {
    id: string;
    status: 'running' | 'paused' | 'ended';
    started_at: string;
    ended_at: string | null;
  } | null;
}

export interface GameSessionChangedEvent extends ChatEventBase {
  type: 'game_session_changed';
  game_session_state: GameSessionState;
}

export type ChatEvent = ChatMessageEvent | ChatMemberJoinedEvent | GameSessionChangedEvent;

export interface ChatHistory {
  campaign_id: string;
  events: ChatEvent[];
  last_sequence: number;
  game_session_state: GameSessionState;
  presence_state: PresenceState;
}

export interface PresenceState {
  epoch: string;
  revision: number;
  online_guest_ids: string[];
}

export function isPresenceState(value: unknown): value is PresenceState {
  return (
    isRecord(value) &&
    typeof value.epoch === 'string' &&
    value.epoch.length > 0 &&
    Number.isSafeInteger(value.revision) &&
    (value.revision as number) >= 0 &&
    Array.isArray(value.online_guest_ids) &&
    value.online_guest_ids.every((id: unknown) => typeof id === 'string')
  );
}

export function isGameSessionState(value: unknown): value is GameSessionState {
  if (!isRecord(value) || !Number.isSafeInteger(value.revision) || (value.revision as number) < 0)
    return false;
  if (value.session === null) return true;
  const session = value.session;
  return (
    isRecord(session) &&
    typeof session.id === 'string' &&
    (session.status === 'running' || session.status === 'paused' || session.status === 'ended') &&
    typeof session.started_at === 'string' &&
    (typeof session.ended_at === 'string' || session.ended_at === null)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function isChatEvent(value: unknown): value is ChatEvent {
  if (!isRecord(value)) {
    return false;
  }
  if (
    value.type !== 'message' &&
    value.type !== 'member_joined' &&
    value.type !== 'game_session_changed'
  ) {
    return false;
  }
  return (
    typeof value.event_id === 'string' &&
    typeof value.campaign_id === 'string' &&
    typeof value.sequence === 'number' &&
    (value.type !== 'game_session_changed' || isGameSessionState(value.game_session_state))
  );
}

/**
 * Merge history and live events into one chronological stream.
 *
 * Server event IDs are unique, so a reconnect snapshot or a replayed frame can
 * never duplicate a rendered event.
 */
export function mergeChatEvents(current: ChatEvent[], incoming: ChatEvent[]): ChatEvent[] {
  const byId = new Map<string, ChatEvent>();
  for (const event of current) {
    byId.set(event.event_id, event);
  }
  for (const event of incoming) {
    if (!byId.has(event.event_id)) {
      byId.set(event.event_id, event);
    }
  }
  return [...byId.values()].sort((left, right) => left.sequence - right.sequence);
}
