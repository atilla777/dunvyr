import { useCallback, useState } from 'react';

import { revokeInvitation, type Campaign, type CampaignMember } from './api';
import { ChatPanel } from './ChatPanel';
import { AdventurePanel } from './AdventurePanel';
import { CharacterPanel } from './CharacterPanel';
import { SceneViewer } from './SceneViewer';
import type { ChatMember } from './chat';
import type { ChatTransportFactory } from './chatSocket';

interface CampaignScreenProps {
  campaign: Campaign;
  currentGuestId: string;
  transportFactory?: ChatTransportFactory;
}

function toCampaignMember(member: ChatMember): CampaignMember | null {
  if (member.role !== 'organizer' && member.role !== 'player') {
    return null;
  }
  return {
    guest_id: member.guest_id,
    nickname: member.nickname,
    role: member.role,
    joined_at: member.joined_at,
  };
}

export function CampaignScreen({
  campaign,
  currentGuestId,
  transportFactory,
}: CampaignScreenProps) {
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  const [invitation, setInvitation] = useState(campaign.invitation);
  const [revokeStatus, setRevokeStatus] = useState<'idle' | 'revoking' | 'failed'>('idle');
  const [members, setMembers] = useState(campaign.members ?? []);
  const handleMemberJoined = useCallback((member: ChatMember) => {
    const nextMember = toCampaignMember(member);
    if (nextMember === null) {
      return;
    }
    setMembers((current) =>
      current.some((existing) => existing.guest_id === nextMember.guest_id)
        ? current
        : [...current, nextMember],
    );
  }, []);
  const isOrganizer = campaign.organizer_id === currentGuestId;
  const secret = invitation.active ? invitation.secret : null;
  const invitationPath = invitation.active
    ? (invitation.path ?? (secret === null ? null : `/join/${secret}`))
    : null;
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

  async function handleRevoke() {
    setRevokeStatus('revoking');
    try {
      const updated = await revokeInvitation(campaign.id);
      setInvitation(updated.invitation);
      setRevokeStatus('idle');
    } catch {
      setRevokeStatus('failed');
    }
  }

  return (
    <section className="campaign" aria-labelledby="campaign-title">
      <h2 id="campaign-title" className="campaign__title">
        {campaign.name}
      </h2>
      <p className="campaign__seats">
        Мест занято: {members.length} из {campaign.max_seats}
      </p>

      <div className="campaign__play">
        <SceneViewer campaignId={campaign.id} />
        <ChatPanel
          campaignId={campaign.id}
          currentGuestId={currentGuestId}
          onMemberJoined={handleMemberJoined}
          transportFactory={transportFactory}
        />
      </div>

      <AdventurePanel campaignId={campaign.id} isOrganizer={isOrganizer} />
      <CharacterPanel campaignId={campaign.id} />

      {isOrganizer && (
        <>
          <h3 className="campaign__subtitle">Ссылка-приглашение</h3>
          {!invitation.active ? (
            <p className="campaign__note">Ссылка отозвана</p>
          ) : invitationUrl === null ? (
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
          {invitation.active && (
            <button
              type="button"
              className="campaign__revoke"
              onClick={handleRevoke}
              disabled={revokeStatus === 'revoking'}
            >
              {revokeStatus === 'revoking' ? 'Отзываем…' : 'Отозвать ссылку'}
            </button>
          )}
          {revokeStatus === 'failed' && (
            <p className="campaign__error" role="alert">
              Не удалось отозвать ссылку. Попробуйте ещё раз.
            </p>
          )}
        </>
      )}

      <h3 className="campaign__subtitle">Участники</h3>
      <ul className="campaign__members">
        {members.map((member) => (
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
