import { useState, type FormEvent } from 'react';

import { createCampaign, type Campaign } from './api';

interface CreateCampaignFormProps {
  onCreated: (campaign: Campaign) => void;
}

export function CreateCampaignForm({ onCreated }: CreateCampaignFormProps) {
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const campaign = await createCampaign(name);
      onCreated(campaign);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Не удалось создать кампанию. Попробуйте ещё раз.',
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="campaign-create" onSubmit={handleSubmit} noValidate>
      <label className="campaign-create__label" htmlFor="campaign-name">
        Название кампании
      </label>
      <input
        id="campaign-name"
        name="campaign-name"
        className="campaign-create__input"
        value={name}
        onChange={(event) => setName(event.target.value)}
        autoComplete="off"
        aria-describedby={error === null ? undefined : 'campaign-create-error'}
        required
      />
      <button type="submit" className="campaign-create__button" disabled={isSubmitting}>
        {isSubmitting ? 'Создаём…' : 'Создать кампанию'}
      </button>
      {error !== null && (
        <p id="campaign-create-error" className="campaign-create__error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
