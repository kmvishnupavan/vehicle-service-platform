import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Clock,
  AlertTriangle,
  Wifi,
  WifiOff,
  RefreshCw,
  MapPin,
  CheckCircle,
  XCircle,
  MessageSquare,
} from 'lucide-react';
import { z } from 'zod';
import { useBooking } from '../hooks/useBookings';
import { TrackingMap } from '../components/map/TrackingMap';
import { MechanicInfoCard } from '../components/booking/MechanicInfoCard';
import { supabase } from '../lib/supabase';
import { api } from '../lib/api';
import {
  subscribeToBookingLocation,
  computeLocationFreshness,
} from '../realtime/bookingLocationChannel';
import { getFriendlyBookingStatus } from '../utils/bookingStatus';
import {
  ChannelStatus,
  LocationFreshness,
  MechanicLocationPayload,
} from '../realtime/types';
import { InspectionReportCard } from '../components/booking/InspectionReportCard';
import { CustomerApprovalModal } from '../components/booking/CustomerApprovalModal';
import { ServiceChecklistProgress } from '../components/booking/ServiceChecklistProgress';
import { ServiceReportCard } from '../components/booking/ServiceReportCard';
import { DisputeModal } from '../components/booking/DisputeModal';
import {
  BookingChecklistItem,
  ServiceReport,
  StructuredInspection,
} from '../types/serviceOperations';

// Zod Schema to strictly validate Realtime Broadcast packets
const LocationPayloadSchema = z.object({
  booking_id: z.string().uuid(),
  mechanic_id: z.string(),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  accuracy_meters: z.number().nullable().optional(),
  recorded_at: z.string(),
  sequence: z.number().int().nonnegative().nullable().optional(),
});

export const BookingTrackingPage: React.FC = () => {
  const { bookingId } = useParams<{ bookingId: string }>();
  const navigate = useNavigate();
  const { data: booking, isLoading, error } = useBooking(bookingId);

  const [currentLocation, setCurrentLocation] = useState<MechanicLocationPayload | null>(null);
  const [freshness, setFreshness] = useState<LocationFreshness>('OFFLINE');
  const [channelStatus, setChannelStatus] = useState<ChannelStatus>('CONNECTING');
  const [secondsAgo, setSecondsAgo] = useState<number | null>(null);
  const [reconnectCount, setReconnectCount] = useState<number>(0);

  // Phase 12: Service Operations State
  const [inspection, setInspection] = useState<StructuredInspection | null>(null);
  const [checklist, setChecklist] = useState<BookingChecklistItem[]>([]);
  const [serviceReport, setServiceReport] = useState<ServiceReport | null>(null);
  const [isApprovalModalOpen, setIsApprovalModalOpen] = useState(false);
  const [isDisputeModalOpen, setIsDisputeModalOpen] = useState(false);

  const channelHandleRef = useRef<any>(null);
  const reconnectTimeoutRef = useRef<any>(null);

  // Timer to continuously update secondsAgo and freshness label
  useEffect(() => {
    const timer = setInterval(() => {
      if (currentLocation?.recorded_at) {
        const recorded = new Date(currentLocation.recorded_at).getTime();
        const elapsed = Math.max(0, Math.floor((Date.now() - recorded) / 1000));
        setSecondsAgo(elapsed);
        setFreshness(computeLocationFreshness(currentLocation.recorded_at));
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [currentLocation]);

  // Initial REST fallback fetch to seed map before first WebSocket packet arrives
  useEffect(() => {
    if (!bookingId) return;

    let isMounted = true;
    api
      .get<any>(`/bookings/${bookingId}/mechanic-location`)
      .then((locData) => {
        if (isMounted && locData?.latitude && locData?.longitude) {
          const payload: MechanicLocationPayload = {
            booking_id: bookingId,
            mechanic_id: locData.mechanic_id,
            latitude: Number(locData.latitude),
            longitude: Number(locData.longitude),
            accuracy_meters: locData.accuracy_meters ? Number(locData.accuracy_meters) : null,
            recorded_at: locData.recorded_at || new Date().toISOString(),
            sequence: 0,
          };
          setCurrentLocation(payload);
          setFreshness(computeLocationFreshness(payload.recorded_at));
        }
      })
      .catch(() => {
        // Fallback endpoint might 400 if mechanic is not assigned yet; handled gracefully
      });

    return () => {
      isMounted = false;
    };
  }, [bookingId]);

  // Phase 12: Fetch Inspection, Checklist & Service Report
  useEffect(() => {
    if (!bookingId) return;

    // Fetch inspection report
    api
      .get<StructuredInspection>(`/bookings/${bookingId}/structured-inspection`)
      .then((data) => setInspection(data))
      .catch(() => setInspection(null));

    // Fetch checklist
    api
      .get<BookingChecklistItem[]>(`/bookings/${bookingId}/checklist`)
      .then((data) => setChecklist(data || []))
      .catch(() => setChecklist([]));

    // Fetch service report if completed
    if (booking?.booking_status && ['service_completed', 'payment_pending', 'paid'].includes(booking.booking_status)) {
      api
        .get<ServiceReport>(`/bookings/${bookingId}/service-report`)
        .then((data) => setServiceReport(data))
        .catch(() => setServiceReport(null));
    }
  }, [bookingId, booking?.booking_status]);

  const handleApproveEstimate = async () => {
    if (!bookingId) return;
    await api.post(`/bookings/${bookingId}/approve-estimate`);
    window.location.reload();
  };

  const handleRejectEstimate = async (reason: string) => {
    if (!bookingId) return;
    // Decline additional work request
    await api.patch(`/bookings/${bookingId}/status`, {
      new_status: 'service_in_progress',
      reason,
    });
    window.location.reload();
  };

  const handleSubmitDispute = async (reason: string) => {
    if (!bookingId) return;
    await api.post(`/bookings/${bookingId}/dispute`, { reason });
    window.location.reload();
  };

  // Realtime Broadcast Channel Subscription
  useEffect(() => {
    if (!bookingId) return;

    // Clean up any existing channel before subscribing
    if (channelHandleRef.current) {
      channelHandleRef.current.unsubscribe();
      channelHandleRef.current = null;
    }

    const isTrackingPermitted =
      booking?.booking_status &&
      ['mechanic_en_route', 'mechanic_arrived', 'service_in_progress', 'additional_work'].includes(
        booking.booking_status
      );

    if (booking && !isTrackingPermitted) {
      setChannelStatus('CLOSED');
      return;
    }

    // Subscribe to private channel booking-location:{booking_id}
    channelHandleRef.current = subscribeToBookingLocation({
      supabaseClient: supabase,
      bookingId,
      onLocation: (rawPayload, newFreshness) => {
        // Strict Zod validation
        const parseResult = LocationPayloadSchema.safeParse(rawPayload);
        if (!parseResult.success) {
          console.warn('Discarded invalid location payload:', parseResult.error);
          return;
        }

        const valid = parseResult.data;
        // Verify booking_id belongs to current route
        if (valid.booking_id !== bookingId) {
          console.warn('Cross-booking location packet rejected.');
          return;
        }

        setCurrentLocation(valid);
        setFreshness(newFreshness);
      },
      onStatusChange: (status) => {
        setChannelStatus(status);

        // Exponential backoff reconnect strategy on disconnect/error
        if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          const delayMs = Math.min(30000, Math.pow(2, reconnectCount) * 1000);
          if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = setTimeout(() => {
            setReconnectCount((c) => c + 1);
          }, delayMs);
        } else if (status === 'SUBSCRIBED') {
          setReconnectCount(0);
        }
      },
      fallbackFetcher: async (bId) => {
        try {
          const res = await api.get<any>(`/bookings/${bId}/mechanic-location`);
          if (res?.latitude && res?.longitude) {
            return {
              booking_id: bId,
              mechanic_id: res.mechanic_id,
              latitude: Number(res.latitude),
              longitude: Number(res.longitude),
              accuracy_meters: res.accuracy_meters ? Number(res.accuracy_meters) : null,
              recorded_at: res.recorded_at,
              sequence: null,
            };
          }
        } catch {
          // Swallow fallback REST errors
        }
        return null;
      },
    });

    return () => {
      if (channelHandleRef.current) {
        channelHandleRef.current.unsubscribe();
        channelHandleRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [bookingId, booking?.booking_status, reconnectCount]);

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-16 flex flex-col items-center justify-center space-y-4">
        <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-semibold text-slate-700">Connecting to live tracking stream...</p>
      </div>
    );
  }

  if (error || !booking) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center">
          <AlertTriangle className="w-8 h-8 text-red-600 mx-auto mb-2" />
          <h2 className="font-bold text-slate-900">Tracking Unavailable</h2>
          <p className="text-xs text-red-700 mt-1">{(error as any)?.message || 'Booking not found.'}</p>
          <Link
            to="/dashboard"
            className="mt-4 inline-block px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold"
          >
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const isCompletedOrCancelled = ['service_completed', 'paid', 'cancelled'].includes(
    booking.booking_status
  );

  const getFreshnessBadge = () => {
    switch (freshness) {
      case 'LIVE':
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 shadow-sm border border-emerald-200">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-600 mr-2 radar-live" />
            LIVE
          </span>
        );
      case 'RECENT':
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800 border border-blue-200">
            <span className="w-2 h-2 rounded-full bg-blue-600 mr-2" />
            RECENT
          </span>
        );
      case 'STALE':
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <span className="w-2 h-2 rounded-full bg-amber-600 mr-2" />
            STALE
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-600 border border-slate-200">
            <WifiOff className="w-3 h-3 mr-1.5 text-slate-400" />
            OFFLINE
          </span>
        );
    }
  };

  // Derive Customer Destination Coordinates
  const customerCoord =
    booking.address?.latitude && booking.address?.longitude
      ? {
          latitude: Number(booking.address.latitude),
          longitude: Number(booking.address.longitude),
          label: booking.address.street_address,
        }
      : null;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-5">
      {/* Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-white p-4 sm:px-6 rounded-2xl border border-slate-200 shadow-sm">
        <div className="flex items-center space-x-3">
          <Link
            to={`/bookings/${booking.id}`}
            className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition"
            title="Back to Booking Details"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">
                Booking #{booking.booking_number}
              </span>
              <span className="text-slate-300">•</span>
              <span
                data-testid="friendly-status-badge"
                className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${getFriendlyBookingStatus(booking.booking_status).badgeClass}`}
              >
                {getFriendlyBookingStatus(booking.booking_status).badgeText}
              </span>
            </div>
            <h1 className="text-lg font-bold text-slate-900 mt-0.5">
              {getFriendlyBookingStatus(booking.booking_status).title}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {getFriendlyBookingStatus(booking.booking_status).subtitle}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3 self-end sm:self-center">
          <Link
            to={`/bookings/${booking.id}/chat`}
            className="inline-flex items-center px-3 py-1.5 rounded-xl text-xs font-semibold bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition shadow-xs"
          >
            <MessageSquare className="w-3.5 h-3.5 mr-1.5 text-emerald-600" />
            Chat with Mechanic
          </Link>

          {channelStatus === 'SUBSCRIBED' ? (
            <span className="flex items-center text-xs text-emerald-700 font-medium">
              <Wifi className="w-3.5 h-3.5 mr-1" />
              Connected
            </span>
          ) : (
            <span className="flex items-center text-xs text-amber-700 font-medium">
              <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
              Connecting...
            </span>
          )}
          {getFreshnessBadge()}
        </div>
      </div>

      {/* Disconnect Fallback Banner */}
      {channelStatus === 'CHANNEL_ERROR' && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 flex items-center justify-between text-xs text-amber-900">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
            <span>
              Realtime live stream temporarily disconnected. Showing latest stored location.
            </span>
          </div>
          <button
            onClick={() => setReconnectCount((c) => c + 1)}
            className="underline font-semibold hover:text-amber-950"
          >
            Reconnect Now
          </button>
        </div>
      )}

      {/* Non-Live Lifecycle Notice */}
      {isCompletedOrCancelled && (
        <div className="bg-slate-100 border border-slate-200 rounded-xl p-4 flex items-center space-x-3 text-slate-700 text-xs">
          {booking.booking_status === 'cancelled' ? (
            <XCircle className="w-5 h-5 text-red-600 flex-shrink-0" />
          ) : (
            <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          )}
          <div>
            <h3 className="font-semibold text-slate-900">
              {booking.booking_status === 'cancelled'
                ? 'Booking Cancelled'
                : 'Service Complete'}
            </h3>
            <p className="mt-0.5 text-slate-500">
              Live location tracking is only active during dispatch and service.
            </p>
          </div>
        </div>
      )}

      {/* Main Grid: Responsive Desktop / Mobile Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (Desktop) / Bottom Column (Mobile): Info Cards */}
        <div className="lg:col-span-1 space-y-4 order-2 lg:order-1">
          {/* Status Progression Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                Service Status
              </h2>
              {secondsAgo !== null && (
                <span className="text-[11px] text-slate-500 flex items-center">
                  <Clock className="w-3 h-3 mr-1 text-slate-400" />
                  {secondsAgo === 0 ? 'Just now' : `${secondsAgo}s ago`}
                </span>
              )}
            </div>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
              <p className="text-xs font-semibold text-slate-800">
                {booking.booking_status === 'mechanic_en_route'
                  ? 'Mechanic is on the way to your vehicle location.'
                  : booking.booking_status === 'mechanic_arrived'
                  ? 'Mechanic has arrived at your destination.'
                  : booking.booking_status === 'service_in_progress'
                  ? 'Vehicle maintenance/repair is currently underway.'
                  : 'Preparing for dispatch.'}
              </p>
              {currentLocation?.accuracy_meters && (
                <p className="text-[10px] text-slate-500 mt-1">
                  GPS precision: ±{Math.round(currentLocation.accuracy_meters)} meters
                </p>
              )}
            </div>

            {/* Destination Address */}
            <div className="pt-2 text-xs text-slate-600 space-y-1">
              <span className="font-semibold text-slate-900 flex items-center">
                <MapPin className="w-3.5 h-3.5 text-emerald-600 mr-1" />
                Service Address
              </span>
              <p className="text-slate-600 pl-4 text-[11px]">
                {booking.address?.street_address || 'Customer Specified Location'}
              </p>
            </div>
          </div>

          {/* Mechanic Card */}
          <MechanicInfoCard
            mechanic={booking.assigned_mechanic}
            bookingStatus={booking.booking_status}
            bookingId={booking.id}
            onOpenChat={() => navigate(`/bookings/${booking.id}/chat`)}
          />
        </div>

        {/* Right Column (Desktop) / Top Column (Mobile): Map */}
        <div className="lg:col-span-2 order-1 lg:order-2">
          <div className="bg-white border border-slate-200 rounded-2xl p-3 shadow-sm h-[480px] sm:h-[540px]">
            <TrackingMap
              customerLocation={customerCoord}
              mechanicLocation={
                currentLocation
                  ? {
                      latitude: currentLocation.latitude,
                      longitude: currentLocation.longitude,
                      accuracy_meters: currentLocation.accuracy_meters,
                    }
                  : null
              }
              freshness={freshness}
            />
          </div>
        </div>
      </div>

      {/* Phase 12: Awaiting Customer Approval Banner */}
      {booking.booking_status === 'awaiting_customer_approval' && (
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-5 text-white flex flex-col sm:flex-row items-center justify-between gap-4 shadow-md">
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-blue-200">Action Required</span>
            <h3 className="text-base font-bold text-white mt-0.5">Technician Estimate Ready for Your Review</h3>
            <p className="text-xs text-blue-100 mt-1 max-w-xl">
              Our technician completed the diagnostic check. Please review the itemized cost breakdown and approve the work to begin service.
            </p>
          </div>
          <button
            onClick={() => setIsApprovalModalOpen(true)}
            className="w-full sm:w-auto px-6 py-2.5 rounded-xl bg-white text-blue-700 font-bold text-xs hover:bg-blue-50 transition shadow-xs flex-shrink-0"
          >
            Review & Authorize (₹{Number(booking.total_amount).toFixed(2)})
          </button>
        </div>
      )}

      {/* Phase 12: Inspection Report Card */}
      {inspection && (
        <InspectionReportCard
          inspection={inspection}
          onOpenApproval={() => setIsApprovalModalOpen(true)}
          showApprovalCta={booking.booking_status === 'awaiting_customer_approval'}
        />
      )}

      {/* Phase 12: Service Execution Checklist Progress */}
      {checklist && checklist.length > 0 && (
        <ServiceChecklistProgress items={checklist} isEditable={false} />
      )}

      {/* Phase 12: Completed Service Report */}
      {serviceReport && (
        <ServiceReportCard
          report={serviceReport}
          onViewInvoice={() => navigate(`/bookings/${booking.id}`)}
        />
      )}

      {/* Dispute Callout for Completed/Paid Bookings */}
      {['service_completed', 'payment_pending', 'paid'].includes(booking.booking_status) && (
        <div className="pt-4 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500">
          <span>Experiencing an unexpected issue with this completed service?</span>
          <button
            onClick={() => setIsDisputeModalOpen(true)}
            className="text-amber-700 hover:text-amber-800 font-semibold underline text-xs"
          >
            Raise a Quality or Billing Dispute
          </button>
        </div>
      )}

      {/* Modals */}
      <CustomerApprovalModal
        isOpen={isApprovalModalOpen}
        onClose={() => setIsApprovalModalOpen(false)}
        bookingNumber={booking.booking_number}
        subtotal={Number(booking.subtotal || 0)}
        additionalCharges={Number(booking.additional_charges || 0)}
        discountAmount={Number(booking.discount_amount || 0)}
        onApprove={handleApproveEstimate}
        onReject={handleRejectEstimate}
      />

      <DisputeModal
        isOpen={isDisputeModalOpen}
        onClose={() => setIsDisputeModalOpen(false)}
        bookingNumber={booking.booking_number}
        onSubmitDispute={handleSubmitDispute}
      />
    </div>
  );
};
