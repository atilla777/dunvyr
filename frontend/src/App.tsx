import { useEffect, useState } from 'react';

import { ApiError, fetchCampaign, fetchCurrentGuest, type Campaign, type Guest } from './api';
import { CampaignScreen } from './CampaignScreen';
import { CreateCampaignForm } from './CreateCampaignForm';
import { invitationSecretFromPath } from './joinPath';
import { JoinScreen } from './JoinScreen';
import { forgetLastCampaign, readLastCampaignId, rememberLastCampaign } from './lastCampaign';
import { LoginForm } from './LoginForm';

type SessionState =
  { status: 'loading' } | { status: 'anonymous' } | { status: 'authenticated'; guest: Guest };

export function App() {
  const [session, setSession] = useState<SessionState>({ status: 'loading' });
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [joinSecret, setJoinSecret] = useState<string | null>(() =>
    invitationSecretFromPath(window.location.pathname),
  );

  useEffect(() => {
    let active = true;
    const initialJoinSecret = invitationSecretFromPath(window.location.pathname);

    async function load() {
      const guest = await fetchCurrentGuest();
      if (!active) {
        return;
      }
      if (guest === null) {
        setSession({ status: 'anonymous' });
        return;
      }

      if (initialJoinSecret === null) {
        const storedCampaignId = readLastCampaignId(guest.id);
        if (storedCampaignId !== null) {
          try {
            const restored = await fetchCampaign(storedCampaignId);
            if (active) {
              setCampaign(restored);
            }
          } catch (error) {
            if (
              active &&
              error instanceof ApiError &&
              (error.status === 403 || error.status === 404)
            ) {
              forgetLastCampaign(guest.id);
            }
          }
        }
      }

      if (active) {
        setSession({ status: 'authenticated', guest });
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, []);

  function handleAuthenticated(guest: Guest) {
    setSession({ status: 'authenticated', guest });
    if (joinSecret !== null) {
      return;
    }
    const storedCampaignId = readLastCampaignId(guest.id);
    if (storedCampaignId === null) {
      return;
    }
    void fetchCampaign(storedCampaignId)
      .then((restored) => setCampaign(restored))
      .catch((error: unknown) => {
        if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
          forgetLastCampaign(guest.id);
        }
      });
  }

  function handleCreated(created: Campaign) {
    if (session.status === 'authenticated') {
      rememberLastCampaign(session.guest.id, created.id);
    }
    setCampaign(created);
  }

  function handleJoined(joined: Campaign) {
    if (session.status === 'authenticated') {
      rememberLastCampaign(session.guest.id, joined.id);
    }
    setCampaign(joined);
    setJoinSecret(null);
    window.history.replaceState(null, '', '/');
  }

  return (
    <main className="app">
      <h1 className="app__title">Dunvyr</h1>
      {session.status === 'loading' && <p className="app__status">Проверяем сессию…</p>}
      {session.status === 'anonymous' && <LoginForm onAuthenticated={handleAuthenticated} />}
      {session.status === 'authenticated' && (
        <>
          <p className="app__status">Вы вошли как {session.guest.nickname}</p>
          {campaign !== null ? (
            <CampaignScreen
              key={campaign.id}
              campaign={campaign}
              currentGuestId={session.guest.id}
            />
          ) : joinSecret !== null ? (
            <JoinScreen secret={joinSecret} onJoined={handleJoined} />
          ) : (
            <CreateCampaignForm onCreated={handleCreated} />
          )}
        </>
      )}
    </main>
  );
}
