import { useState } from 'react';

import { joinCampaign, type Campaign } from './api';

interface JoinScreenProps {
  secret: string;
  onJoined: (campaign: Campaign) => void;
}

export function JoinScreen({ secret, onJoined }: JoinScreenProps) {
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleJoin() {
    setError(null);
    setIsSubmitting(true);
    try {
      const campaign = await joinCampaign(secret);
      onJoined(campaign);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Не удалось присоединиться к кампании. Попробуйте ещё раз.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="join" aria-labelledby="join-title">
      <h2 id="join-title" className="join__title">
        Присоединение к кампании
      </h2>
      <p className="join__note">Вы открыли ссылку-приглашение. Присоединяйтесь к кампании.</p>
      <button type="button" className="join__button" onClick={handleJoin} disabled={isSubmitting}>
        {isSubmitting ? 'Присоединяемся…' : 'Присоединиться'}
      </button>
      {error !== null && (
        <p className="join__error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
