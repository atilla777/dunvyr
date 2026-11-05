const LAST_CAMPAIGN_PREFIX = 'dunvyr:campaign:';

function storageKey(guestId: string): string {
  return `${LAST_CAMPAIGN_PREFIX}${guestId}`;
}

/**
 * Remember only the campaign id per guest. It is not a secret: access still
 * requires the guest session cookie, so an id in localStorage grants nothing.
 */
export function rememberLastCampaign(guestId: string, campaignId: string): void {
  try {
    window.localStorage.setItem(storageKey(guestId), campaignId);
  } catch {
    // Private-mode or disabled storage must not break the campaign flow.
  }
}

export function readLastCampaignId(guestId: string): string | null {
  try {
    return window.localStorage.getItem(storageKey(guestId));
  } catch {
    return null;
  }
}

export function forgetLastCampaign(guestId: string): void {
  try {
    window.localStorage.removeItem(storageKey(guestId));
  } catch {
    // Nothing to clean up when storage is unavailable.
  }
}
