import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';

import { fetchChatHistory } from './api';
import {
  isGameSessionState,
  isPresenceState,
  isQueueState,
  mergeChatEvents,
  type ChatEvent,
  type ChatMember,
  type GameSessionState,
  type PresenceState,
  type QueueState,
} from './chat';
import {
  createChatTransport,
  type ChatConnectionStatus,
  type ChatTransport,
  type ChatTransportFactory,
} from './chatSocket';

export const CHAT_MESSAGE_MAX_LENGTH = 2000;

interface ChatPanelProps {
  campaignId: string;
  currentGuestId: string;
  onMemberJoined?: (member: ChatMember) => void;
  onSessionState?: (state: GameSessionState) => void;
  onConnection?: (status: ChatConnectionStatus) => void;
  onPresenceState?: (state: PresenceState) => void;
  onQueueState?: (state: QueueState) => void;
  onProposalsChanged?: () => void;
  onCheckChanged?: () => void;
  transportFactory?: ChatTransportFactory;
}

type HistoryStatus = 'loading' | 'ready' | 'error';

function serverErrorMessage(code: string): string {
  if (code === 'forbidden') {
    return 'Нет доступа к чату этой кампании.';
  }
  if (code === 'invalid_message') {
    return 'Сообщение отклонено. Проверьте текст.';
  }
  return 'Не удалось отправить сообщение. Попробуйте ещё раз.';
}

function connectionMessage(status: ChatConnectionStatus): string {
  if (status === 'open') {
    return 'Чат на связи';
  }
  if (status === 'connecting') {
    return 'Подключаемся к чату…';
  }
  if (status === 'reconnecting') {
    return 'Соединение с чатом потеряно. Восстанавливаем…';
  }
  if (status === 'closed') {
    return 'Соединение с чатом потеряно. Восстановить не удалось. Обновите страницу.';
  }
  return 'Ошибка соединения с чатом. Обновите страницу.';
}

export function ChatPanel({
  campaignId,
  currentGuestId,
  onMemberJoined,
  onSessionState,
  onConnection,
  onPresenceState,
  onQueueState,
  onProposalsChanged,
  onCheckChanged,
  transportFactory,
}: ChatPanelProps) {
  const [events, setEvents] = useState<ChatEvent[]>([]);
  const [draft, setDraft] = useState('');
  const [historyStatus, setHistoryStatus] = useState<HistoryStatus>('loading');
  const [connection, setConnection] = useState<ChatConnectionStatus>('connecting');
  const [error, setError] = useState<string | null>(null);
  const seenEventIds = useRef(new Set<string>());
  const lastSequence = useRef(0);
  const hasSnapshot = useRef(false);
  const transportRef = useRef<ChatTransport | null>(null);
  const onMemberJoinedRef = useRef(onMemberJoined);
  const onSessionStateRef = useRef(onSessionState);
  const onConnectionRef = useRef(onConnection);
  const onPresenceStateRef = useRef(onPresenceState);
  const onQueueStateRef = useRef(onQueueState);
  const onProposalsChangedRef = useRef(onProposalsChanged);
  const onCheckChangedRef = useRef(onCheckChanged);
  const presenceRef = useRef<PresenceState | null>(null);
  useEffect(() => {
    onMemberJoinedRef.current = onMemberJoined;
  }, [onMemberJoined]);
  useEffect(() => {
    onSessionStateRef.current = onSessionState;
    onConnectionRef.current = onConnection;
    onPresenceStateRef.current = onPresenceState;
    onQueueStateRef.current = onQueueState;
    onProposalsChangedRef.current = onProposalsChanged;
    onCheckChangedRef.current = onCheckChanged;
  }, [
    onSessionState,
    onConnection,
    onPresenceState,
    onQueueState,
    onProposalsChanged,
    onCheckChanged,
  ]);

  /**
   * Merge server events exactly once per `event_id`. The same event can arrive
   * from the initial snapshot, the live stream and a reconnect snapshot; the
   * seen set is shared by all three sources.
   */
  const acceptEvents = useCallback((incoming: ChatEvent[], notifyMembers: boolean) => {
    const fresh: ChatEvent[] = [];
    for (const event of incoming) {
      if (seenEventIds.current.has(event.event_id)) {
        continue;
      }
      seenEventIds.current.add(event.event_id);
      fresh.push(event);
    }
    if (fresh.length === 0) {
      return;
    }
    setEvents((current) => mergeChatEvents(current, fresh));
    if (notifyMembers) {
      for (const event of fresh) {
        if (event.type === 'member_joined') {
          onMemberJoinedRef.current?.(event.member);
        }
      }
    }
  }, []);

  useEffect(() => {
    let active = true;
    seenEventIds.current = new Set();
    lastSequence.current = 0;
    hasSnapshot.current = false;
    presenceRef.current = null;
    const factory = transportFactory ?? createChatTransport;
    const transport = factory(campaignId, {
      onEvent: (event) => {
        if (active) {
          if (event.type === 'game_session_changed')
            onSessionStateRef.current?.(event.game_session_state);
          if (event.type === 'queue_changed') onQueueStateRef.current?.(event.queue_state);
          if (event.type === 'check_resolved') onCheckChangedRef.current?.();
          acceptEvents([event], true);
        }
      },
      onStatus: (status) => {
        if (active) {
          setConnection(status);
          onConnectionRef.current?.(status);
        }
      },
      onPresence: (state) => {
        const current = presenceRef.current;
        if (
          active &&
          current !== null &&
          current.epoch === state.epoch &&
          state.revision > current.revision
        ) {
          presenceRef.current = state;
          onPresenceStateRef.current?.(state);
        }
      },
      onServerError: (code) => {
        if (active) {
          setError(serverErrorMessage(code));
        }
      },
      onProposalsChanged: () => {
        if (active) onProposalsChangedRef.current?.();
      },
      onResync: async (signal) => {
        const after = hasSnapshot.current ? lastSequence.current : undefined;
        try {
          const history = await fetchChatHistory(campaignId, after, signal);
          if (!active || signal.aborted) return;
          if (!isPresenceState(history.presence_state))
            throw new Error('Invalid presence snapshot');
          presenceRef.current = history.presence_state;
          onPresenceStateRef.current?.(history.presence_state);
          if (onSessionStateRef.current) {
            if (!isGameSessionState(history.game_session_state))
              throw new Error('Invalid session snapshot');
            onSessionStateRef.current(history.game_session_state);
          }
          if (onQueueStateRef.current) {
            if (!isQueueState(history.queue_state)) throw new Error('Invalid queue snapshot');
            onQueueStateRef.current(history.queue_state);
          }
          for (const event of history.events) {
            lastSequence.current = Math.max(lastSequence.current, event.sequence);
          }
          hasSnapshot.current = true;
          if (onCheckChangedRef.current) onCheckChangedRef.current();
          else onProposalsChangedRef.current?.();
          acceptEvents(history.events, true);
          setHistoryStatus('ready');
        } catch (error) {
          if (active && !signal.aborted) setHistoryStatus('error');
          throw error;
        }
      },
    });
    transportRef.current = transport;
    return () => {
      active = false;
      transportRef.current = null;
      transport.close();
    };
  }, [campaignId, transportFactory, acceptEvents]);

  function handleSubmit(submitEvent: FormEvent<HTMLFormElement>) {
    submitEvent.preventDefault();
    const content = draft.trim();
    if (content.length === 0) {
      setError('Введите сообщение.');
      return;
    }
    if (content.length > CHAT_MESSAGE_MAX_LENGTH) {
      setError(`Сообщение должно быть не длиннее ${CHAT_MESSAGE_MAX_LENGTH} символов.`);
      return;
    }
    const sent = transportRef.current?.sendMessage(content) ?? false;
    if (!sent) {
      setError('Чат не подключён. Сообщение не отправлено.');
      return;
    }
    setDraft('');
    setError(null);
  }

  const historyMessage =
    historyStatus === 'loading'
      ? 'Загружаем историю чата…'
      : historyStatus === 'error'
        ? 'Не удалось загрузить историю чата. Попробуйте обновить страницу.'
        : null;

  return (
    <section className="chat" aria-labelledby="chat-title">
      <h3 id="chat-title" className="chat__title">
        Чат
      </h3>
      <p className="chat__status" aria-live="polite">
        {connectionMessage(connection)}
      </p>
      {historyMessage !== null && (
        <p className="chat__note" aria-live="polite">
          {historyMessage}
        </p>
      )}

      <ol className="chat__messages" aria-label="Сообщения чата">
        {events.map((event) =>
          event.type === 'message' ? (
            <li
              key={event.event_id}
              className={
                event.message.author_id === currentGuestId
                  ? 'chat__message chat__message--own'
                  : 'chat__message'
              }
            >
              <span className="chat__author">
                {event.message.author_id === currentGuestId ? 'Вы' : event.message.author_nickname}
              </span>
              <span className="chat__text">{event.message.content}</span>
            </li>
          ) : event.type === 'member_joined' ? (
            <li key={event.event_id} className="chat__system">
              {event.member.nickname} присоединился к кампании
            </li>
          ) : event.type === 'check_resolved' ? (
            <li key={event.event_id} className="chat__system">
              Проверка: {event.result.success ? 'Успех' : 'Неудача'}. Кубики:{' '}
              {event.result.dice.join(', ')}. {event.result.characteristic} + {event.result.skill} +
              ({event.result.dice.join(' + ')}) + {event.result.modifier} = {event.result.total} /{' '}
              {event.result.difficulty}
            </li>
          ) : null,
        )}
      </ol>
      {events.length === 0 && historyStatus === 'ready' && (
        <p className="chat__empty">Сообщений пока нет. Напишите первым.</p>
      )}

      <form className="chat__form" onSubmit={handleSubmit}>
        <label className="chat__label" htmlFor="chat-input">
          Сообщение
        </label>
        <textarea
          id="chat-input"
          className="chat__input"
          value={draft}
          maxLength={CHAT_MESSAGE_MAX_LENGTH}
          rows={2}
          onChange={(changeEvent) => setDraft(changeEvent.target.value)}
        />
        <button type="submit" className="chat__send">
          Отправить
        </button>
      </form>
      {error !== null && (
        <p className="chat__error" aria-live="assertive">
          {error}
        </p>
      )}
    </section>
  );
}
