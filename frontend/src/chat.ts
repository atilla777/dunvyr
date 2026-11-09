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

export interface QueueState {
  version: number;
  queue: null | {
    encounter_id: string;
    participants: { guest_id: string; character_id: string }[];
    round_order: string[];
    round_number: number;
    cursor: number;
    skipped: string[];
    current_guest_id: string | null;
  };
}

export interface QueueChangedEvent extends ChatEventBase {
  type: 'queue_changed';
  queue_state: QueueState;
}

export interface CheckResult {
  dice: number[];
  characteristic: number;
  skill: number;
  modifier: number;
  difficulty: number;
  total: number;
  success: boolean;
}

export function isCheckResult(value: unknown): value is CheckResult {
  return (
    isRecord(value) &&
    Array.isArray(value.dice) &&
    value.dice.length === 4 &&
    value.dice.every((die: unknown) => die === -1 || die === 0 || die === 1) &&
    ['characteristic', 'skill', 'modifier', 'difficulty', 'total'].every((key) =>
      Number.isSafeInteger(value[key]),
    ) &&
    typeof value.success === 'boolean'
  );
}

export interface CheckResolvedEvent extends ChatEventBase {
  type: 'check_resolved';
  result: CheckResult;
}

export interface NarrationState {
  result_event_id: string;
  state: 'pending' | 'generating' | 'ready' | 'failed';
  revision: number;
  text: string | null;
  error: string | null;
}

export interface NarrationChangedEvent extends ChatEventBase {
  type: 'narration_changed';
  narration: NarrationState;
}

export function isNarrationState(value: unknown): value is NarrationState {
  return (
    isRecord(value) &&
    typeof value.result_event_id === 'string' &&
    ['pending', 'generating', 'ready', 'failed'].includes(String(value.state)) &&
    Number.isSafeInteger(value.revision) &&
    (value.revision as number) >= 1 &&
    (value.text === null || (typeof value.text === 'string' && [...value.text].length <= 4500)) &&
    (value.error === null || value.error === 'retryable_provider_error') &&
    (value.state !== 'ready' || typeof value.text === 'string')
  );
}

export function newerQueueState(current: QueueState | null, incoming: QueueState): QueueState {
  return current === null || incoming.version > current.version ? incoming : current;
}

export type ChatEvent =
  | ChatMessageEvent
  | ChatMemberJoinedEvent
  | GameSessionChangedEvent
  | QueueChangedEvent
  | CheckResolvedEvent
  | NarrationChangedEvent;

export interface ChatHistory {
  campaign_id: string;
  events: ChatEvent[];
  last_sequence: number;
  game_session_state: GameSessionState;
  presence_state: PresenceState;
  queue_state: QueueState;
  narration_events?: NarrationChangedEvent[];
}

export function isQueueState(value: unknown): value is QueueState {
  if (!isRecord(value) || !Number.isSafeInteger(value.version) || (value.version as number) < 0)
    return false;
  if (value.queue === null) return true;
  const q = value.queue;
  return (
    isRecord(q) &&
    typeof q.encounter_id === 'string' &&
    Array.isArray(q.participants) &&
    q.participants.every(
      (p: unknown) =>
        isRecord(p) && typeof p.guest_id === 'string' && typeof p.character_id === 'string',
    ) &&
    Array.isArray(q.round_order) &&
    q.round_order.every((id: unknown) => typeof id === 'string') &&
    Number.isSafeInteger(q.round_number) &&
    (q.round_number as number) > 0 &&
    Number.isSafeInteger(q.cursor) &&
    (q.cursor as number) >= 0 &&
    Array.isArray(q.skipped) &&
    q.skipped.every((id: unknown) => typeof id === 'string') &&
    (q.current_guest_id === null || typeof q.current_guest_id === 'string')
  );
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
    value.type !== 'game_session_changed' &&
    value.type !== 'queue_changed' &&
    value.type !== 'check_resolved' &&
    value.type !== 'narration_changed'
  ) {
    return false;
  }
  return (
    typeof value.event_id === 'string' &&
    typeof value.campaign_id === 'string' &&
    typeof value.sequence === 'number' &&
    (value.type !== 'game_session_changed' || isGameSessionState(value.game_session_state)) &&
    (value.type !== 'queue_changed' || isQueueState(value.queue_state)) &&
    (value.type !== 'narration_changed' || isNarrationState(value.narration)) &&
    (value.type !== 'check_resolved' || isCheckResult(value.result))
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
  const latest = new Map<string, NarrationChangedEvent>();
  for (const event of byId.values()) {
    if (event.type !== 'narration_changed') continue;
    const previous = latest.get(event.narration.result_event_id);
    if (
      !previous ||
      (previous.narration.state !== 'ready' &&
        event.narration.revision > previous.narration.revision)
    ) {
      latest.set(event.narration.result_event_id, event);
    }
  }
  return [...byId.values()]
    .filter(
      (event) =>
        event.type !== 'narration_changed' ||
        latest.get(event.narration.result_event_id)?.event_id === event.event_id,
    )
    .sort((left, right) => left.sequence - right.sequence);
}
