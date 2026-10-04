import React, { useEffect, useState } from 'react';
import {
  Clock,
  MapPin,
  Wrench,
  CheckCircle,
  XCircle,
  AlertCircle,
  Navigation,
} from 'lucide-react';

export interface IncomingJobOffer {
  assignment_id: string;
  booking_id: string;
  booking_number: string;
  service_name: string;
  customer_area: string;
  distance_km: number;
  estimated_arrival_minutes: number;
  expires_at: string;
  attempt_number?: number;
}

interface IncomingJobOfferCardProps {
  offer: IncomingJobOffer;
  onAccept: (assignmentId: string) => Promise<void>;
  onDecline: (assignmentId: string, reason?: string) => Promise<void>;
}

export const IncomingJobOfferCard: React.FC<IncomingJobOfferCardProps> = ({
  offer,
  onAccept,
  onDecline,
}) => {
  const [secondsRemaining, setSecondsRemaining] = useState<number>(() => {
    const expiry = new Date(offer.expires_at).getTime();
    return Math.max(0, Math.floor((expiry - Date.now()) / 1000));
  });
  const [isAccepting, setIsAccepting] = useState(false);
  const [isDeclining, setIsDeclining] = useState(false);

  useEffect(() => {
    const timer = setInterval(() => {
      const expiry = new Date(offer.expires_at).getTime();
      const left = Math.max(0, Math.floor((expiry - Date.now()) / 1000));
      setSecondsRemaining(left);
      if (left <= 0) {
        clearInterval(timer);
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [offer.expires_at]);

  const isExpired = secondsRemaining <= 0;
  const progressPercent = Math.min(100, Math.max(0, (secondsRemaining / 60) * 100));

  const handleAccept = async () => {
    if (isExpired || isAccepting || isDeclining) return;
    setIsAccepting(true);
    try {
      await onAccept(offer.assignment_id);
    } finally {
      setIsAccepting(false);
    }
  };

  const handleDecline = async () => {
    if (isExpired || isAccepting || isDeclining) return;
    setIsDeclining(true);
    try {
      await onDecline(offer.assignment_id, 'Unavailable at this time');
    } finally {
      setIsDeclining(false);
    }
  };

  return (
    <div
      data-testid="incoming-job-offer-card"
      className={`relative overflow-hidden rounded-2xl border-2 transition-all shadow-lg ${
        isExpired
          ? 'bg-slate-50 border-slate-300 opacity-75'
          : 'bg-white border-amber-400 ring-4 ring-amber-100/70 animate-pulse-subtle'
      }`}
    >
      {/* Top Expiration Bar */}
      <div className="h-1.5 w-full bg-slate-100">
        <div
          className={`h-full transition-all duration-1000 ${
            secondsRemaining < 15
              ? 'bg-rose-500'
              : secondsRemaining < 30
              ? 'bg-amber-500'
              : 'bg-emerald-500'
          }`}
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      <div className="p-5 sm:p-6">
        {/* Header with Countdown */}
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-amber-500 text-white shadow-sm">
              <Wrench className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-amber-700 bg-amber-100/80 px-2 py-0.5 rounded-full border border-amber-200">
                New Job Offer
              </span>
              <h3 className="text-base font-extrabold text-slate-900 mt-1">
                {offer.service_name}
              </h3>
            </div>
          </div>

          <div
            data-testid="offer-countdown"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold ${
              isExpired
                ? 'bg-slate-200 text-slate-600 border-slate-300'
                : secondsRemaining < 15
                ? 'bg-rose-100 text-rose-800 border-rose-300 animate-bounce'
                : 'bg-amber-100 text-amber-900 border-amber-300'
            }`}
          >
            <Clock className="w-4 h-4" />
            <span>{isExpired ? 'Offer Expired' : `${secondsRemaining}s remaining`}</span>
          </div>
        </div>

        {/* Location & Routing Details */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 bg-slate-50/80 rounded-xl border border-slate-200/80 text-xs text-slate-700 mb-5">
          <div className="flex items-center gap-2">
            <MapPin className="w-4 h-4 text-slate-400 shrink-0" />
            <div className="truncate">
              <span className="text-slate-500 block text-[10px] uppercase font-semibold">Location Area</span>
              <span className="font-semibold text-slate-800 truncate">{offer.customer_area || 'Doorstep Service'}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Navigation className="w-4 h-4 text-indigo-500 shrink-0" />
            <div>
              <span className="text-slate-500 block text-[10px] uppercase font-semibold">Distance</span>
              <span className="font-semibold text-slate-800">{offer.distance_km} km away</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-emerald-500 shrink-0" />
            <div>
              <span className="text-slate-500 block text-[10px] uppercase font-semibold">Estimated ETA</span>
              <span className="font-semibold text-slate-800">~{offer.estimated_arrival_minutes} mins road transit</span>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        {isExpired ? (
          <div className="flex items-center justify-center gap-2 text-xs font-semibold text-slate-500 py-2">
            <AlertCircle className="w-4 h-4 text-slate-400" />
            <span>This offer has expired and has been reassigned to another technician.</span>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <button
              type="button"
              data-testid="accept-offer-button"
              disabled={isAccepting || isDeclining}
              onClick={handleAccept}
              className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm shadow-md hover:shadow-lg transition disabled:opacity-50"
            >
              <CheckCircle className="w-4 h-4" />
              <span>{isAccepting ? 'Accepting...' : 'Accept Job'}</span>
            </button>

            <button
              type="button"
              data-testid="decline-offer-button"
              disabled={isAccepting || isDeclining}
              onClick={handleDecline}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-white hover:bg-rose-50 text-slate-600 hover:text-rose-700 border border-slate-300 hover:border-rose-300 font-semibold text-sm transition disabled:opacity-50"
            >
              <XCircle className="w-4 h-4" />
              <span>{isDeclining ? 'Declining...' : 'Decline'}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
