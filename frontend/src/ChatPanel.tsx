import { useEffect, useRef, useState, type FormEvent } from 'react';

import { fetchChatHistory } from './api';
import { mergeChatEvents, type ChatEvent, type ChatMember } from './chat';
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
  if (status === 'closed') {
    return 'Соединение с чатом потеряно. Обновите страницу.';
  }
  return 'Ошибка соединения с чатом. Обновите страницу.';
}

export function ChatPanel({
  campaignId,
  currentGuestId,
  onMemberJoined,
  transportFactory,
}: ChatPanelProps) {
  const [events, setEvents] = useState<ChatEvent[]>([]);
  const [draft, setDraft] = useState('');
  const [historyStatus, setHistoryStatus] = useState<HistoryStatus>('loading');
  const [connection, setConnection] = useState<ChatConnectionStatus>('connecting');
  const [error, setError] = useState<string | null>(null);
  const seenEventIds = useRef(new Set<string>());
  const transportRef = useRef<ChatTransport | null>(null);
  const onMemberJoinedRef = useRef(onMemberJoined);

  useEffect(() => {
    onMemberJoinedRef.current = onMemberJoined;
  }, [onMemberJoined]);

  useEffect(() => {
    let active = true;
    fetchChatHistory(campaignId)
      .then((history) => {
        if (!active) {
          return;
        }
        for (const event of history.events) {
          seenEventIds.current.add(event.event_id);
        }
        setEvents((current) => mergeChatEvents(current, history.events));
        setHistoryStatus('ready');
      })
      .catch(() => {
        if (active) {
          setHistoryStatus('error');
        }
      });
    return () => {
      active = false;
    };
  }, [campaignId]);

  useEffect(() => {
    let active = true;
    const factory = transportFactory ?? createChatTransport;
    const transport = factory(campaignId, {
      onEvent: (event) => {
        if (!active || seenEventIds.current.has(event.event_id)) {
          return;
        }
        seenEventIds.current.add(event.event_id);
        setEvents((current) => mergeChatEvents(current, [event]));
        if (event.type === 'member_joined') {
          onMemberJoinedRef.current?.(event.member);
        }
      },
      onStatus: (status) => {
        if (active) {
          setConnection(status);
        }
      },
      onServerError: (code) => {
        if (active) {
          setError(serverErrorMessage(code));
        }
      },
    });
    transportRef.current = transport;
    return () => {
      active = false;
      transportRef.current = null;
      transport.close();
    };
  }, [campaignId, transportFactory]);

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
      setError('Чат не подключён. Сообщение не отправлено; обновите страницу.');
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
          ) : (
            <li key={event.event_id} className="chat__system">
              {event.member.nickname} присоединился к кампании
            </li>
          ),
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
