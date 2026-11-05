import { useState } from 'react';

import type { Campaign } from './api';

interface CampaignScreenProps {
  campaign: Campaign;
  currentGuestId: string;
}

export function CampaignScreen({ campaign, currentGuestId }: CampaignScreenProps) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  const secret = campaign.invitation.secret;
  const invitationPath = campaign.invitation.path ?? (secret === null ? null : `/join/${secret}`);
  const invitationUrl =
    invitationPath === null ? null : new URL(invitationPath, window.location.origin).toString();

  async function handleCopy() {
    if (invitationUrl === null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(invitationUrl);
      setCopyStatus('copied');
    } catch {
      setCopyStatus('failed');
    }
  }

  return (
    <section className="campaign" aria-labelledby="campaign-title">
      <h2 id="campaign-title" className="campaign__title">
        {campaign.name}
      </h2>
      <p className="campaign__seats">
        Мест занято: {campaign.members.length} из {campaign.max_seats}
      </p>

      <h3 className="campaign__subtitle">Ссылка-приглашение</h3>
      {invitationUrl === null ? (
        <p className="campaign__note">
          Ссылка-приглашение показывается только один раз при создании кампании.
        </p>
      ) : (
        <>
          <p className="campaign__invitation">
            <a href={invitationUrl}>{invitationUrl}</a>
          </p>
          <button type="button" className="campaign__copy" onClick={handleCopy}>
            Скопировать ссылку
          </button>
          {copyStatus === 'copied' && (
            <p className="campaign__copy-status" role="status">
              Ссылка скопирована
            </p>
          )}
          {copyStatus === 'failed' && (
            <p className="campaign__copy-status campaign__error" role="alert">
              Не удалось скопировать ссылку. Выделите её вручную.
            </p>
          )}
        </>
      )}

      <h3 className="campaign__subtitle">Участники</h3>
      <ul className="campaign__members">
        {campaign.members.map((member) => (
          <li key={member.guest_id} className="campaign__member">
            <span className="campaign__member-name">{member.nickname}</span>
            {member.role === 'organizer' && (
              <span className="campaign__member-role"> — организатор</span>
            )}
            {member.guest_id === currentGuestId && (
              <span className="campaign__member-self"> (вы)</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
