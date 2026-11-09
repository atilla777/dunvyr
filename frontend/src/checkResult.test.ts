import { expect, it } from 'vitest';
import { isChatEvent, isCheckResult } from './chat';

it('accepts a public resolved check and rejects malformed dice', () => {
  const result = {
    dice: [-1, 0, 1, 1],
    characteristic: 2,
    skill: 2,
    modifier: 0,
    difficulty: 5,
    total: 5,
    success: true,
  };
  expect(isCheckResult(result)).toBe(true);
  expect(isCheckResult({ ...result, dice: [0, 0, 0, 2] })).toBe(false);
  expect(
    isChatEvent({
      type: 'check_resolved',
      event_id: 'e',
      campaign_id: 'c',
      sequence: 3,
      occurred_at: '',
      result,
    }),
  ).toBe(true);
});
