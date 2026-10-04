/**
 * Realtime Location Types (Phase 8.2B).
 *
 * Defines contracts for ephemeral live mechanic location streaming,
 * channel state machine transitions, sequence validation, and staleness categories.
 */

export interface MechanicLocationPayload {
  booking_id: string;
  mechanic_id: string;
  latitude: number;
  longitude: number;
  accuracy_meters?: number | null;
  recorded_at: string;
  sequence?: number | null;
}

export type ChannelStatus =
  | 'CONNECTING'
  | 'SUBSCRIBED'
  | 'CHANNEL_ERROR'
  | 'TIMED_OUT'
  | 'CLOSED';

export type LocationFreshness =
  | 'LIVE'     // 0 - 10 seconds since recorded_at
  | 'RECENT'   // 10 - 30 seconds since recorded_at
  | 'STALE'    // 30+ seconds since recorded_at
  | 'OFFLINE'; // Disconnected / no data

export interface LocationFreshnessThresholds {
  liveThresholdSeconds: number;   // default: 10
  recentThresholdSeconds: number; // default: 30
}

export interface BookingLocationSubscriptionOptions {
  supabaseClient: any; // SupabaseClient instance
  bookingId: string;
  onLocation: (location: MechanicLocationPayload, freshness: LocationFreshness) => void;
  onStatusChange?: (status: ChannelStatus, error?: Error) => void;
  freshnessThresholds?: LocationFreshnessThresholds;
  fallbackFetcher?: (bookingId: string) => Promise<MechanicLocationPayload | null>;
}

export interface BookingLocationChannelHandle {
  unsubscribe: () => Promise<void>;
  getLatestSequence: () => number;
  getLatestLocation: () => MechanicLocationPayload | null;
  getFreshness: () => LocationFreshness;
}
