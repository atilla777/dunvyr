import type { ChatHistory } from './chat';

export interface Guest {
  id: string;
  nickname: string;
}

export type CampaignMemberRole = 'organizer' | 'player';

export interface CampaignMember {
  guest_id: string;
  nickname: string;
  role: CampaignMemberRole;
  joined_at: string;
}

export interface CampaignInvitation {
  active: boolean;
  // Populated only by the successful create response; later reads omit it.
  secret: string | null;
  path: string | null;
}

export interface Campaign {
  id: string;
  name: string;
  max_seats: number;
  organizer_id: string;
  created_at: string;
  members: CampaignMember[];
  invitation: CampaignInvitation;
}

export interface CreateCampaignOptions {
  maxSeats?: number;
  idempotencyKey?: string;
}

export interface Adventure {
  adventure_id: string;
  fingerprint: string;
  title: string;
  description: string;
}

export interface CatalogAdventure extends Adventure {
  edition: string;
}

export type AdventureState =
  { status: 'waiting'; adventure: null } | { status: 'pinned'; adventure: Adventure };

export class AdventureError extends Error {
  constructor(
    message: string,
    readonly code?: string,
  ) {
    super(message);
  }
}

async function adventureRequest<T>(campaignId: string, suffix: string, body?: object): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}/${suffix}`, {
      credentials: 'same-origin',
      ...(body === undefined
        ? {}
        : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }),
    });
  } catch {
    throw new AdventureError(NETWORK_ERROR);
  }
  if (!response.ok) {
    const detail = await readErrorDetail(response);
    if (response.status === 409 && detail === 'stale_fingerprint') {
      throw new AdventureError(
        'Версия приключения изменилась. Обновите каталог и выберите снова.',
        detail,
      );
    }
    if (response.status === 409 && detail === 'adventure_conflict') {
      throw new AdventureError(
        'Приключение уже выбрано другим запросом. Обновите состояние.',
        detail,
      );
    }
    if (response.status === 429) {
      const retry = response.headers.get('Retry-After');
      throw new AdventureError(
        `Слишком много попыток. Попробуйте позже${retry && /^\d+$/.test(retry) ? ` (через ${retry} сек.)` : ''}.`,
      );
    }
    throw new AdventureError(
      response.status === 403
        ? CAMPAIGN_FORBIDDEN
        : 'Не удалось загрузить или выбрать приключение. Попробуйте ещё раз.',
    );
  }
  return (await response.json()) as T;
}

export function fetchAdventure(campaignId: string): Promise<AdventureState> {
  return adventureRequest(campaignId, 'adventure');
}

export async function fetchAdventureCatalog(campaignId: string): Promise<CatalogAdventure[]> {
  const result = await adventureRequest<{ adventures: CatalogAdventure[] }>(
    campaignId,
    'adventures',
  );
  return result.adventures;
}

export function selectAdventure(
  campaignId: string,
  adventure: CatalogAdventure,
): Promise<AdventureState> {
  return adventureRequest(campaignId, 'adventure', {
    adventure_id: adventure.adventure_id,
    fingerprint: adventure.fingerprint,
  });
}

const GENERIC_ERROR = 'Не удалось выполнить запрос. Попробуйте ещё раз.';
const NETWORK_ERROR = 'Не удалось связаться с сервером. Попробуйте ещё раз.';
const NICKNAME_ERROR = 'Псевдоним должен содержать от 1 до 32 символов без управляющих символов.';
const CAMPAIGN_NAME_ERROR =
  'Название кампании должно содержать от 1 до 60 символов без управляющих символов.';
const SEATS_ERROR = 'Число мест должно быть от 2 до 20.';
const CAMPAIGN_FORBIDDEN = 'Нет доступа к этой кампании.';
const CAMPAIGN_NOT_FOUND = 'Кампания не найдена.';
const INVITATION_NOT_FOUND = 'Ссылка-приглашение не найдена или отозвана.';
const CAMPAIGN_FULL = 'В кампании нет свободных мест.';
const NICKNAME_TAKEN = 'Этот псевдоним уже занят в кампании.';
const JOIN_INVALID = 'Не удалось присоединиться к кампании. Проверьте ссылку.';
const JOIN_RATE_LIMIT = 'Слишком много попыток присоединиться. Попробуйте позже.';
const REVOKE_RATE_LIMIT = 'Слишком много попыток. Попробуйте позже.';
const CHAT_FORBIDDEN = 'Нет доступа к чату этой кампании.';
const CHAT_UNAVAILABLE = 'Не удалось загрузить историю чата. Попробуйте обновить страницу.';

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function readErrorDetail(
  response: Response,
  validationMessage: string = GENERIC_ERROR,
): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string' &&
      body.detail.length > 0
    ) {
      return response.status === 422 ? validationMessage : body.detail;
    }
  } catch {
    // Fall through to the generic message below.
  }
  return GENERIC_ERROR;
}

function invitationValidationMessage(response: Response): Promise<string> {
  return readErrorDetail(response, CAMPAIGN_NAME_ERROR);
}

function randomHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((value) => value.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Idempotency keys only need uniqueness, not secrecy. getRandomValues works in
 * insecure LAN HTTP contexts where crypto.randomUUID is unavailable.
 */
export function createIdempotencyKey(): string {
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = randomHex(bytes);
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function fetchCurrentGuest(): Promise<Guest | null> {
  try {
    const response = await fetch('/api/identity/me', {
      credentials: 'same-origin',
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Guest;
  } catch {
    return null;
  }
}

export async function createSession(nickname: string): Promise<Guest> {
  let response: Response;
  try {
    response = await fetch('/api/identity/sessions', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname }),
    });
  } catch {
    throw new ApiError(NETWORK_ERROR);
  }

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response, NICKNAME_ERROR));
  }
  return (await response.json()) as Guest;
}

export async function createCampaign(
  name: string,
  options: CreateCampaignOptions = {},
): Promise<Campaign> {
  const payload: { name: string; max_seats?: number } = { name };
  if (options.maxSeats !== undefined) {
    payload.max_seats = options.maxSeats;
  }
  let response: Response;
  try {
    response = await fetch('/api/campaigns', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': options.idempotencyKey ?? createIdempotencyKey(),
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError(NETWORK_ERROR);
  }

  if (!response.ok) {
    if (response.status === 429) {
      throw new ApiError('Слишком много попыток создать кампанию. Попробуйте позже.');
    }
    if (
      response.status === 422 &&
      options.maxSeats !== undefined &&
      (options.maxSeats < 2 || options.maxSeats > 20)
    ) {
      throw new ApiError(SEATS_ERROR);
    }
    throw new ApiError(await invitationValidationMessage(response));
  }
  return (await response.json()) as Campaign;
}

export async function fetchCampaign(campaignId: string): Promise<Campaign> {
  let response: Response;
  try {
    response = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}`, {
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError(NETWORK_ERROR);
  }

  if (response.status === 403) {
    throw new ApiError(CAMPAIGN_FORBIDDEN, response.status);
  }
  if (response.status === 404) {
    throw new ApiError(CAMPAIGN_NOT_FOUND, response.status);
  }
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as Campaign;
}

export async function joinCampaign(secret: string): Promise<Campaign> {
  let response: Response;
  try {
    response = await fetch('/api/campaigns/join', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ secret }),
    });
  } catch {
    throw new ApiError(NETWORK_ERROR);
  }

  if (!response.ok) {
    if (response.status === 429) {
      throw new ApiError(JOIN_RATE_LIMIT);
    }
    if (response.status === 404) {
      throw new ApiError(INVITATION_NOT_FOUND);
    }
    if (response.status === 403) {
      throw new ApiError(CAMPAIGN_FORBIDDEN);
    }
    if (response.status === 422) {
      throw new ApiError(JOIN_INVALID);
    }
    if (response.status === 409) {
      const detail = await readErrorDetail(response);
      if (detail === 'campaign_full') {
        throw new ApiError(CAMPAIGN_FULL);
      }
      if (detail === 'nickname_taken') {
        throw new ApiError(NICKNAME_TAKEN);
      }
      throw new ApiError(detail);
    }
    throw new ApiError(await readErrorDetail(response));
  }
  return (await response.json()) as Campaign;
}

/**
 * Fetch the chat snapshot. Without a cursor the server returns the latest
 * slice; `afterSequence` asks only for events the client has not seen yet.
 */
export async function fetchChatHistory(
  campaignId: string,
  afterSequence?: number,
  signal?: AbortSignal,
): Promise<ChatHistory> {
  const query = afterSequence === undefined ? '' : `?after=${String(afterSequence)}`;
  let response: Response;
  try {
    response = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}/chat/events${query}`, {
      credentials: 'same-origin',
      signal,
    });
  } catch {
    throw new ApiError(CHAT_UNAVAILABLE);
  }

  if (response.status === 403) {
    throw new ApiError(CHAT_FORBIDDEN, response.status);
  }
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }
  return (await response.json()) as ChatHistory;
}

export async function revokeInvitation(campaignId: string): Promise<Campaign> {
  let response: Response;
  try {
    response = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}/invitation/revoke`, {
      method: 'POST',
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError(NETWORK_ERROR);
  }

  if (!response.ok) {
    if (response.status === 429) {
      throw new ApiError(REVOKE_RATE_LIMIT);
    }
    if (response.status === 403) {
      throw new ApiError(CAMPAIGN_FORBIDDEN);
    }
    if (response.status === 404) {
      throw new ApiError(CAMPAIGN_NOT_FOUND);
    }
    throw new ApiError(await readErrorDetail(response));
  }
  return (await response.json()) as Campaign;
}
