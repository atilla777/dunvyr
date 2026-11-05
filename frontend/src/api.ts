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

const GENERIC_ERROR = 'Не удалось выполнить запрос. Попробуйте ещё раз.';
const NETWORK_ERROR = 'Не удалось связаться с сервером. Попробуйте ещё раз.';
const NICKNAME_ERROR = 'Псевдоним должен содержать от 1 до 32 символов без управляющих символов.';
const CAMPAIGN_NAME_ERROR =
  'Название кампании должно содержать от 1 до 60 символов без управляющих символов.';
const SEATS_ERROR = 'Число мест должно быть от 2 до 20.';
const CAMPAIGN_FORBIDDEN = 'Нет доступа к этой кампании.';
const CAMPAIGN_NOT_FOUND = 'Кампания не найдена.';

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
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
    throw new ApiError(CAMPAIGN_FORBIDDEN);
  }
  if (response.status === 404) {
    throw new ApiError(CAMPAIGN_NOT_FOUND);
  }
  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response));
  }
  return (await response.json()) as Campaign;
}
