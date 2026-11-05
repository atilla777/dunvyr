export interface Guest {
  id: string;
  nickname: string;
}

const GENERIC_ERROR = 'Не удалось выполнить запрос. Попробуйте ещё раз.';
const NETWORK_ERROR = 'Не удалось связаться с сервером. Попробуйте ещё раз.';
const NICKNAME_ERROR = 'Псевдоним должен содержать от 1 до 32 символов без управляющих символов.';

export class ApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string' &&
      body.detail.length > 0
    ) {
      return response.status === 422 ? NICKNAME_ERROR : body.detail;
    }
  } catch {
    // Fall through to the generic message below.
  }
  return GENERIC_ERROR;
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
    throw new ApiError(await readErrorDetail(response));
  }
  return (await response.json()) as Guest;
}
