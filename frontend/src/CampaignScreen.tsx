import { useCallback, useState } from 'react';

import { revokeInvitation, type Campaign, type CampaignMember } from './api';
import { ChatPanel } from './ChatPanel';
import { AdventurePanel } from './AdventurePanel';
import { CharacterPanel } from './CharacterPanel';
import { SceneViewer } from './SceneViewer';
import { LocationMap } from './LocationMap';
import { EncounterCatalog } from './EncounterCatalog';
import {
  isCheckResult,
  isQueueState,
  newerQueueState,
  type CheckResult,
  type ChatMember,
  type PresenceState,
  type QueueState,
} from './chat';
import type { ChatTransportFactory } from './chatSocket';
import type { ChatConnectionStatus } from './chatSocket';
import { GameSessionPanel } from './GameSessionPanel';
import { useGameSession } from './useGameSession';
import { QueuePanel } from './QueuePanel';
import { useProposals } from './useProposals';
import { ProposalsPanel } from './ProposalsPanel';

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
  const [connection, setConnection] = useState<ChatConnectionStatus>('connecting');
  const [presence, setPresence] = useState<PresenceState | null>(null);
  const [queue, setQueue] = useState<QueueState | null>(null);
  const [result, setResult] = useState<CheckResult | null>(null);
  const [progressionRevision, setProgressionRevision] = useState(0);
  const acceptQueue = useCallback(
    (next: QueueState) => setQueue((current) => newerQueueState(current, next)),
    [],
  );
  const refreshAfterCheck = useCallback(() => {
    setProgressionRevision((value) => value + 1);
    const base = `/api/campaigns/${encodeURIComponent(campaign.id)}`;
    void fetch(`${base}/queue`, { credentials: 'same-origin', cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: unknown) => {
        if (isQueueState(data)) acceptQueue(data);
      })
      .catch(() => undefined);
    void fetch(`${base}/check-result`, { credentials: 'same-origin', cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data: { result?: unknown }) => {
        if (isCheckResult(data.result)) setResult(data.result);
      })
      .catch(() => undefined);
  }, [campaign.id, acceptQueue]);
  const gameSession = useGameSession(campaign.id);
  const proposals = useProposals(
    campaign.id,
    currentGuestId,
    queue,
    acceptQueue,
    gameSession.state,
    gameSession.refresh,
    connection,
    refreshAfterCheck,
    result !== null,
  );
  const refreshProposals = proposals.refresh;
  const handleCheckChanged = useCallback(() => {
    refreshAfterCheck();
    void refreshProposals();
  }, [refreshAfterCheck, refreshProposals]);
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
      <GameSessionPanel controller={gameSession} organizer={isOrganizer} connection={connection} />

      <div className="campaign__play">
        <div>
          <SceneViewer campaignId={campaign.id} revision={progressionRevision} />
          <LocationMap campaignId={campaign.id} />
          <EncounterCatalog
            campaignId={campaign.id}
            onPrepare={(selection) => proposals.execute('create', selection)}
            prepareDisabled={!proposals.ready || (proposals.state?.proposals.length ?? 0) >= 20}
            revision={progressionRevision}
          />
          {result && (
            <section aria-label="Результат проверки">
              <h3>Результат проверки: {result.success ? 'Успех' : 'Неудача'}</h3>
              <p>Кубики: {result.dice.join(', ')}</p>
              <p>
                {result.characteristic} + {result.skill} + ({result.dice.join(' + ')}) +{' '}
                {result.modifier} = {result.total} / {result.difficulty}
              </p>
            </section>
          )}
          <ProposalsPanel campaignId={campaign.id} controller={proposals} />
          <QueuePanel
            campaignId={campaign.id}
            currentGuestId={currentGuestId}
            members={members}
            state={queue}
            accept={acceptQueue}
            session={gameSession.state}
            presence={presence}
            connection={connection}
            completed={result !== null}
          />
        </div>
        <ChatPanel
          campaignId={campaign.id}
          currentGuestId={currentGuestId}
          onMemberJoined={handleMemberJoined}
          onSessionState={gameSession.accept}
          onConnection={setConnection}
          onPresenceState={setPresence}
          onQueueState={acceptQueue}
          onProposalsChanged={proposals.refresh}
          onCheckChanged={handleCheckChanged}
          transportFactory={transportFactory}
        />
      </div>

      <AdventurePanel campaignId={campaign.id} isOrganizer={isOrganizer} />
      <CharacterPanel campaignId={campaign.id} onCharacter={proposals.setCharacter} />

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
            <span className="campaign__member-presence">
              {' — '}
              {connection !== 'open' || presence === null
                ? 'Статус неизвестен'
                : presence.online_guest_ids.includes(member.guest_id)
                  ? 'В сети'
                  : 'Не в сети'}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
