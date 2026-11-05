import { useEffect, useState } from 'react';

import { fetchCurrentGuest, type Campaign, type Guest } from './api';
import { CampaignScreen } from './CampaignScreen';
import { CreateCampaignForm } from './CreateCampaignForm';
import { LoginForm } from './LoginForm';

type SessionState =
  { status: 'loading' } | { status: 'anonymous' } | { status: 'authenticated'; guest: Guest };

export function App() {
  const [session, setSession] = useState<SessionState>({ status: 'loading' });
  const [campaign, setCampaign] = useState<Campaign | null>(null);

  useEffect(() => {
    let active = true;
    void fetchCurrentGuest().then((guest) => {
      if (!active) {
        return;
      }
      setSession(guest === null ? { status: 'anonymous' } : { status: 'authenticated', guest });
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="app">
      <h1 className="app__title">Dunvyr</h1>
      {session.status === 'loading' && <p className="app__status">Проверяем сессию…</p>}
      {session.status === 'anonymous' && (
        <LoginForm onAuthenticated={(guest) => setSession({ status: 'authenticated', guest })} />
      )}
      {session.status === 'authenticated' && (
        <>
          <p className="app__status">Вы вошли как {session.guest.nickname}</p>
          {campaign === null ? (
            <CreateCampaignForm onCreated={setCampaign} />
          ) : (
            <CampaignScreen campaign={campaign} currentGuestId={session.guest.id} />
          )}
        </>
      )}
    </main>
  );
}
