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

export type ChatEvent = ChatMessageEvent | ChatMemberJoinedEvent;

export interface ChatHistory {
  campaign_id: string;
  events: ChatEvent[];
  last_sequence: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function isChatEvent(value: unknown): value is ChatEvent {
  if (!isRecord(value)) {
    return false;
  }
  if (value.type !== 'message' && value.type !== 'member_joined') {
    return false;
  }
  return (
    typeof value.event_id === 'string' &&
    typeof value.campaign_id === 'string' &&
    typeof value.sequence === 'number'
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
