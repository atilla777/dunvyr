const JOIN_PATH_PATTERN = /^\/join\/([^/]+)\/?$/;

/** Extract the invitation secret from a `/join/<secret>` browser path. */
export function invitationSecretFromPath(pathname: string): string | null {
  const match = JOIN_PATH_PATTERN.exec(pathname);
  if (match === null) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}
