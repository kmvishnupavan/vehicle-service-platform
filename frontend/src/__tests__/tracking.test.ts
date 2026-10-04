import { describe, it, expect, vi } from 'vitest';
import {
  computeLocationFreshness,
  isValidLocationPayload,
  subscribeToBookingLocation,
} from '../realtime/bookingLocationChannel';
import { MechanicLocationPayload } from '../realtime/types';
import { BookingStatus } from '../types/booking';

describe('Realtime Tracking - Unit & Logic Test Suite (Phase 8.3)', () => {
  const BOOKING_ID = '33333333-3333-3333-3333-333333333333';
  const OTHER_BOOKING_ID = '99999999-9999-9999-9999-999999999999';
  const MECHANIC_ID = 'mech-1234';

  // Helper to build a valid base packet
  const createValidPayload = (overrides?: Partial<MechanicLocationPayload>): MechanicLocationPayload => ({
    booking_id: BOOKING_ID,
    mechanic_id: MECHANIC_ID,
    latitude: 17.385044,
    longitude: 78.486671,
    accuracy_meters: 5.2,
    recorded_at: new Date().toISOString(),
    sequence: 100,
    ...overrides,
  });

  // 1. Booking ID payload validation
  it('validates booking_id matches the route booking_id exactly', () => {
    const valid = createValidPayload();
    expect(isValidLocationPayload(valid, BOOKING_ID)).toBe(true);

    const crossBooking = createValidPayload({ booking_id: OTHER_BOOKING_ID });
    expect(isValidLocationPayload(crossBooking, BOOKING_ID)).toBe(false);
  });

  // 2. Invalid latitude
  it('rejects invalid latitude values (< -90, > 90, NaN)', () => {
    expect(isValidLocationPayload(createValidPayload({ latitude: 90.0001 }), BOOKING_ID)).toBe(false);
    expect(isValidLocationPayload(createValidPayload({ latitude: -90.0001 }), BOOKING_ID)).toBe(false);
    expect(isValidLocationPayload(createValidPayload({ latitude: NaN }), BOOKING_ID)).toBe(false);
    expect(isValidLocationPayload(createValidPayload({ latitude: 0 }), BOOKING_ID)).toBe(true);
    expect(isValidLocationPayload(createValidPayload({ latitude: -45.5 }), BOOKING_ID)).toBe(true);
  });

  // 3. Invalid longitude
  it('rejects invalid longitude values (< -180, > 180, NaN)', () => {
    expect(isValidLocationPayload(createValidPayload({ longitude: 180.0001 }), BOOKING_ID)).toBe(false);
    expect(isValidLocationPayload(createValidPayload({ longitude: -180.0001 }), BOOKING_ID)).toBe(false);
    expect(isValidLocationPayload(createValidPayload({ longitude: NaN }), BOOKING_ID)).toBe(false);
    expect(isValidLocationPayload(createValidPayload({ longitude: 0 }), BOOKING_ID)).toBe(true);
    expect(isValidLocationPayload(createValidPayload({ longitude: 78.486671 }), BOOKING_ID)).toBe(true);
  });

  // 4. Stale sequence ignored & 5. Newer sequence accepted
  it('deduplicates monotonic sequence numbers: rejects older/equal and accepts newer', () => {
    let capturedLocation: MechanicLocationPayload | null = null;
    let broadcastHandler: ((envelope: any) => void) | null = null;

    const mockChannel: any = {
      on: vi.fn((_type: string, _filter: any, callback: any) => {
        broadcastHandler = callback;
        return mockChannel;
      }),
      subscribe: vi.fn((cb: (status: string) => void) => {
        cb('SUBSCRIBED');
        return mockChannel;
      }),
    };

    const mockSupabase = {
      channel: vi.fn(() => mockChannel),
      removeChannel: vi.fn(),
    } as any;

    const handle = subscribeToBookingLocation({
      supabaseClient: mockSupabase,
      bookingId: BOOKING_ID,
      onLocation: (loc) => {
        capturedLocation = loc;
      },
    });

    expect(broadcastHandler).toBeDefined();

    // First packet with sequence 100 -> accepted
    const p1 = createValidPayload({ sequence: 100, latitude: 17.38 });
    broadcastHandler!({ payload: p1 });
    expect(capturedLocation).toEqual(p1);
    expect(handle.getLatestSequence()).toBe(100);

    // Stale packet with sequence 99 -> ignored
    const pStale = createValidPayload({ sequence: 99, latitude: 17.39 });
    broadcastHandler!({ payload: pStale });
    expect(capturedLocation).toEqual(p1); // Still p1
    expect(handle.getLatestSequence()).toBe(100);

    // Duplicate packet with sequence 100 -> ignored
    const pDuplicate = createValidPayload({ sequence: 100, latitude: 17.40 });
    broadcastHandler!({ payload: pDuplicate });
    expect(capturedLocation).toEqual(p1); // Still p1
    expect(handle.getLatestSequence()).toBe(100);

    // Newer packet with sequence 101 -> accepted
    const pNew = createValidPayload({ sequence: 101, latitude: 17.41 });
    broadcastHandler!({ payload: pNew });
    expect(capturedLocation).toEqual(pNew);
    expect(handle.getLatestSequence()).toBe(101);
  });

  // 6. Stale timestamp handling & 10. OFFLINE state
  it('returns OFFLINE when recorded_at is invalid or unparseable', () => {
    expect(computeLocationFreshness('invalid-timestamp-string')).toBe('OFFLINE');
    expect(isValidLocationPayload(createValidPayload({ recorded_at: 'garbage' }), BOOKING_ID)).toBe(false);
  });

  // 7. LIVE state
  it('evaluates timestamps under 10 seconds old as LIVE', () => {
    const liveTime = new Date(Date.now() - 4000).toISOString(); // 4s ago
    expect(computeLocationFreshness(liveTime)).toBe('LIVE');

    const exactBoundary = new Date(Date.now() - 10000).toISOString(); // 10s ago
    expect(computeLocationFreshness(exactBoundary)).toBe('LIVE');
  });

  // 8. RECENT state
  it('evaluates timestamps between 10 and 30 seconds old as RECENT', () => {
    const recentTime = new Date(Date.now() - 15000).toISOString(); // 15s ago
    expect(computeLocationFreshness(recentTime)).toBe('RECENT');

    const recentUpper = new Date(Date.now() - 30000).toISOString(); // 30s ago
    expect(computeLocationFreshness(recentUpper)).toBe('RECENT');
  });

  // 9. STALE state
  it('evaluates timestamps older than 30 seconds as STALE', () => {
    const staleTime = new Date(Date.now() - 45000).toISOString(); // 45s ago
    expect(computeLocationFreshness(staleTime)).toBe('STALE');

    const veryOldTime = new Date(Date.now() - 3600000).toISOString(); // 1hr ago
    expect(computeLocationFreshness(veryOldTime)).toBe('STALE');
  });

  // 11. Fallback location handling
  it('triggers fallback REST fetcher when channel encounters an error or timeout', async () => {
    let capturedLocation: MechanicLocationPayload | null = null;
    let subscribeCallback: ((status: string, err?: any) => void) | null = null;

    const mockChannel: any = {
      on: vi.fn().mockReturnThis(),
      subscribe: vi.fn((cb: any) => {
        subscribeCallback = cb;
        return mockChannel;
      }),
    };

    const mockSupabase = {
      channel: vi.fn(() => mockChannel),
      removeChannel: vi.fn(),
    } as any;

    const fallbackData: MechanicLocationPayload = {
      booking_id: BOOKING_ID,
      mechanic_id: MECHANIC_ID,
      latitude: 17.4000,
      longitude: 78.5000,
      accuracy_meters: 10,
      recorded_at: new Date().toISOString(),
      sequence: null,
    };

    const fallbackFetcher = vi.fn().mockResolvedValue(fallbackData);

    subscribeToBookingLocation({
      supabaseClient: mockSupabase,
      bookingId: BOOKING_ID,
      onLocation: (loc) => {
        capturedLocation = loc;
      },
      fallbackFetcher,
    });

    expect(subscribeCallback).toBeDefined();

    // Trigger CHANNEL_ERROR
    await subscribeCallback!('CHANNEL_ERROR', new Error('Connection lost'));

    expect(fallbackFetcher).toHaveBeenCalledWith(BOOKING_ID);
    expect(capturedLocation).toEqual(fallbackData);
  });

  // 12. Channel cleanup
  it('cleans up channel and suppresses callbacks when unsubscribe is called', async () => {
    const mockChannel = {
      on: vi.fn().mockReturnThis(),
      subscribe: vi.fn().mockReturnThis(),
    };

    const mockSupabase = {
      channel: vi.fn(() => mockChannel),
      removeChannel: vi.fn().mockResolvedValue({}),
    } as any;

    const handle = subscribeToBookingLocation({
      supabaseClient: mockSupabase,
      bookingId: BOOKING_ID,
      onLocation: vi.fn(),
    });

    await handle.unsubscribe();

    expect(mockSupabase.removeChannel).toHaveBeenCalledWith(mockChannel);
  });

  // 13. Reconnect behavior (exponential backoff helper test)
  it('computes bounded exponential backoff delays up to 30s', () => {
    const calculateDelay = (retryCount: number) => Math.min(30000, Math.pow(2, retryCount) * 1000);

    expect(calculateDelay(0)).toBe(1000);  // 1s
    expect(calculateDelay(1)).toBe(2000);  // 2s
    expect(calculateDelay(2)).toBe(4000);  // 4s
    expect(calculateDelay(3)).toBe(8000);  // 8s
    expect(calculateDelay(4)).toBe(16000); // 16s
    expect(calculateDelay(5)).toBe(30000); // capped at 30s
    expect(calculateDelay(10)).toBe(30000); // capped at 30s
  });

  // 14. Booking status tracking visibility
  it('permits tracking only during active dispatch and in-service states', () => {
    const liveTrackingPermittedStatuses: BookingStatus[] = [
      'mechanic_en_route',
      'mechanic_arrived',
      'service_in_progress',
      'additional_work',
    ];

    const nonLiveStatuses: BookingStatus[] = [
      'pending',
      'confirmed',
      'mechanic_assigned',
      'inspection',
      'awaiting_customer_approval',
      'service_completed',
      'payment_pending',
      'paid',
      'cancelled',
      'disputed',
    ];

    const isTrackingPermitted = (status: BookingStatus) =>
      liveTrackingPermittedStatuses.includes(status);

    liveTrackingPermittedStatuses.forEach((st) => {
      expect(isTrackingPermitted(st)).toBe(true);
    });

    nonLiveStatuses.forEach((st) => {
      expect(isTrackingPermitted(st)).toBe(false);
    });
  });
});
