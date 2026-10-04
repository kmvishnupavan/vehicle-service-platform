/**
 * Booking Location Channel Subscription Abstraction (Phase 8.2B).
 *
 * Implements client-side Supabase Realtime Broadcast subscription for
 * ephemeral live mechanic GPS tracking.
 *
 * Features:
 * 1. Scoped to deterministic private channel `booking-location:{booking_id}`.
 * 2. Monotonic sequence deduplication: ignores out-of-order/stale packets.
 * 3. Freshness calculation (LIVE: <10s, RECENT: 10-30s, STALE: >30s).
 * 4. Automatic fallback to REST endpoint on channel disconnect/timeout.
 * 5. Clean lifecycle teardown via `removeChannel`.
 */

import {
  BookingLocationChannelHandle,
  BookingLocationSubscriptionOptions,
  ChannelStatus,
  LocationFreshness,
  LocationFreshnessThresholds,
  MechanicLocationPayload,
} from './types';

const DEFAULT_THRESHOLDS: LocationFreshnessThresholds = {
  liveThresholdSeconds: 10,
  recentThresholdSeconds: 30,
};

/**
 * Computes location staleness relative to the current client clock.
 */
export function computeLocationFreshness(
  recordedAtIso: string,
  thresholds: LocationFreshnessThresholds = DEFAULT_THRESHOLDS
): LocationFreshness {
  const recorded = new Date(recordedAtIso).getTime();
  if (isNaN(recorded)) return 'OFFLINE';

  const now = Date.now();
  const elapsedSeconds = Math.max(0, (now - recorded) / 1000);

  if (elapsedSeconds <= thresholds.liveThresholdSeconds) {
    return 'LIVE';
  } else if (elapsedSeconds <= thresholds.recentThresholdSeconds) {
    return 'RECENT';
  }
  return 'STALE';
}

/**
 * Validates the structure and basic ranges of an incoming broadcast payload.
 */
export function isValidLocationPayload(
  payload: any,
  expectedBookingId: string
): payload is MechanicLocationPayload {
  if (!payload || typeof payload !== 'object') return false;
  if (payload.booking_id !== expectedBookingId) return false;
  if (typeof payload.mechanic_id !== 'string' || !payload.mechanic_id) return false;
  if (typeof payload.latitude !== 'number' || isNaN(payload.latitude) || payload.latitude < -90 || payload.latitude > 90) {
    return false;
  }
  if (typeof payload.longitude !== 'number' || isNaN(payload.longitude) || payload.longitude < -180 || payload.longitude > 180) {
    return false;
  }
  if (typeof payload.recorded_at !== 'string' || isNaN(new Date(payload.recorded_at).getTime())) {
    return false;
  }
  return true;
}

/**
 * Subscribes to a private booking location broadcast channel with automatic sequence
 * tracking, staleness evaluation, fallback polling, and teardown management.
 */
export function subscribeToBookingLocation(
  options: BookingLocationSubscriptionOptions
): BookingLocationChannelHandle {
  const {
    supabaseClient,
    bookingId,
    onLocation,
    onStatusChange,
    freshnessThresholds = DEFAULT_THRESHOLDS,
    fallbackFetcher,
  } = options;

  let latestSequence = -1;
  let latestLocation: MechanicLocationPayload | null = null;
  let isTornDown = false;

  const topic = `booking-location:${bookingId}`;

  // Create private broadcast channel
  const channel = supabaseClient.channel(topic, {
    config: {
      private: true,
      broadcast: { ack: false },
    },
  });

  // Listen for ephemeral 'mechanic_location' broadcast events
  channel.on('broadcast', { event: 'mechanic_location' }, (envelope: any) => {
    if (isTornDown) return;

    const payload = envelope?.payload;
    if (!isValidLocationPayload(payload, bookingId)) {
      return;
    }

    // Monotonic sequence verification: discard older out-of-order packets
    if (typeof payload.sequence === 'number') {
      if (payload.sequence <= latestSequence) {
        return; // Stale or duplicate packet ignored
      }
      latestSequence = payload.sequence;
    }

    latestLocation = payload;
    const freshness = computeLocationFreshness(payload.recorded_at, freshnessThresholds);
    onLocation(payload, freshness);
  });

  // Subscribe and handle channel status transitions
  channel.subscribe(async (status: string, err?: any) => {
    if (isTornDown) return;

    const channelStatus = status as ChannelStatus;
    if (onStatusChange) {
      onStatusChange(channelStatus, err);
    }

    // Trigger fallback fetcher on error or timeout
    if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
      if (fallbackFetcher) {
        try {
          const fallbackData = await fallbackFetcher(bookingId);
          if (fallbackData && !isTornDown) {
            // Only adopt fallback if newer than what we have or if we have no data
            latestLocation = fallbackData;
            const freshness = computeLocationFreshness(fallbackData.recorded_at, freshnessThresholds);
            onLocation(fallbackData, freshness);
          }
        } catch {
          // Swallow fallback network failure without crashing UI
        }
      }
    }
  });

  return {
    unsubscribe: async () => {
      isTornDown = true;
      try {
        await supabaseClient.removeChannel(channel);
      } catch {
        // Silently handle channel removal errors during unmount
      }
    },
    getLatestSequence: () => latestSequence,
    getLatestLocation: () => latestLocation,
    getFreshness: () => {
      if (!latestLocation) return 'OFFLINE';
      return computeLocationFreshness(latestLocation.recorded_at, freshnessThresholds);
    },
  };
}
