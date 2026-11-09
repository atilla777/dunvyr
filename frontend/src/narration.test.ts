import { describe, expect, it } from 'vitest';
import { isChatEvent, mergeChatEvents, type NarrationChangedEvent } from './chat';

const event = (
  revision: number,
  state: NarrationChangedEvent['narration']['state'],
): NarrationChangedEvent => ({
  type: 'narration_changed',
  event_id: `event-${revision}`,
  campaign_id: 'campaign',
  sequence: revision + 5,
  occurred_at: '2026-11-09T12:00:00Z',
  narration: {
    result_event_id: 'result',
    revision,
    state,
    text: state === 'ready' ? '<script>not markup</script>' : null,
    error: state === 'failed' ? 'retryable_provider_error' : null,
  },
});

describe('narration stream merge', () => {
  it('reduces snapshots, duplicate and out-of-order statuses to the newest correlation', () => {
    const current = mergeChatEvents(
      [event(3, 'failed')],
      [event(1, 'pending'), event(3, 'failed')],
    );
    expect(current).toEqual([event(3, 'failed')]);
    expect(mergeChatEvents(current, [event(5, 'generating'), event(4, 'pending')])).toEqual([
      event(5, 'generating'),
    ]);
    expect(mergeChatEvents([event(6, 'ready')], [event(5, 'generating')])).toEqual([
      event(6, 'ready'),
    ]);
  });
  it('rejects malformed public state and accepts plain text', () => {
    expect(isChatEvent(event(6, 'ready'))).toBe(true);
    expect(isChatEvent({ ...event(6, 'ready'), narration: { state: 'ready' } })).toBe(false);
    const ready = event(6, 'ready');
    expect(
      isChatEvent({
        ...ready,
        narration: { ...ready.narration, text: 'a'.repeat(2800) + '🌒'.repeat(1200) },
      }),
    ).toBe(true);
  });
});
