import { useState, type FormEvent } from 'react';

import { createSession, type Guest } from './api';

interface LoginFormProps {
  onAuthenticated: (guest: Guest) => void;
}

export function LoginForm({ onAuthenticated }: LoginFormProps) {
  const [nickname, setNickname] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const guest = await createSession(nickname);
      onAuthenticated(guest);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось войти. Попробуйте ещё раз.');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="login" onSubmit={handleSubmit} noValidate>
      <label className="login__label" htmlFor="nickname">
        Псевдоним
      </label>
      <input
        id="nickname"
        name="nickname"
        className="login__input"
        value={nickname}
        onChange={(event) => setNickname(event.target.value)}
        autoComplete="nickname"
        aria-describedby={error === null ? undefined : 'login-error'}
        required
      />
      <button type="submit" className="login__button" disabled={isSubmitting}>
        {isSubmitting ? 'Входим…' : 'Войти'}
      </button>
      {error !== null && (
        <p id="login-error" className="login__error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
