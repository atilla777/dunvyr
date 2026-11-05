import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Campaign } from './api';
import { CampaignScreen } from './CampaignScreen';

const CURRENT_GUEST_ID = '11111111-1111-4111-8111-111111111111';

const campaign: Campaign = {
  id: '22222222-2222-4222-8222-222222222222',
  name: 'Ночная смена',
  max_seats: 6,
  organizer_id: CURRENT_GUEST_ID,
  created_at: '2026-01-01T12:00:00+00:00',
  members: [
    {
      guest_id: CURRENT_GUEST_ID,
      nickname: 'Алиса',
      role: 'organizer',
      joined_at: '2026-01-01T12:00:00+00:00',
    },
    {
      guest_id: '33333333-3333-4333-8333-333333333333',
      nickname: 'Боб',
      role: 'player',
      joined_at: '2026-01-01T12:05:00+00:00',
    },
  ],
  invitation: { active: true, secret: 'invitation-secret', path: '/join/invitation-secret' },
};

function stubClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
}

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(navigator, 'clipboard');
});

describe('CampaignScreen', () => {
  it('shows the absolute invitation link and copies it to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    stubClipboard(writeText);
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    const invitationUrl = new URL('/join/invitation-secret', window.location.origin).toString();

    expect(screen.getByRole('heading', { level: 2, name: 'Ночная смена' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: invitationUrl })).toHaveAttribute(
      'href',
      invitationUrl,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Скопировать ссылку' }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(invitationUrl));
    expect(await screen.findByRole('status')).toHaveTextContent('Ссылка скопирована');
  });

  it('lists the organizer and marks the current guest', () => {
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    expect(screen.getByText('Мест занято: 2 из 6')).toBeInTheDocument();
    expect(screen.getByText('Алиса')).toBeInTheDocument();
    expect(screen.getByText('— организатор')).toBeInTheDocument();
    expect(screen.getByText('(вы)')).toBeInTheDocument();
    expect(screen.getByText('Боб')).toBeInTheDocument();
    expect(screen.getAllByText('— организатор')).toHaveLength(1);
  });

  it('does not repeat the secret when the campaign is read later', () => {
    render(
      <CampaignScreen
        campaign={{ ...campaign, invitation: { active: true, secret: null, path: null } }}
        currentGuestId={CURRENT_GUEST_ID}
      />,
    );

    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Скопировать ссылку' })).not.toBeInTheDocument();
    expect(
      screen.getByText('Ссылка-приглашение показывается только один раз при создании кампании.'),
    ).toBeInTheDocument();
  });

  it('reports a clipboard failure without hiding the link', async () => {
    stubClipboard(vi.fn().mockRejectedValue(new Error('denied')));
    render(<CampaignScreen campaign={campaign} currentGuestId={CURRENT_GUEST_ID} />);

    fireEvent.click(screen.getByRole('button', { name: 'Скопировать ссылку' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Не удалось скопировать ссылку. Выделите её вручную.',
    );
    expect(screen.getByRole('link')).toBeInTheDocument();
  });
});
