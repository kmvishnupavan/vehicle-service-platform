import React from 'react';
import { ArrowLeft, Wifi, WifiOff, RefreshCw, ShieldCheck, Wrench } from 'lucide-react';
import { Link } from 'react-router-dom';

interface Props {
  bookingId: string;
  bookingNumber: string | null;
  participantName: string | null;
  participantRole: string | null;
  connectionStatus: string;
  canSendMessages: boolean;
}

export const ChatHeader: React.FC<Props> = ({
  bookingId,
  bookingNumber,
  participantName,
  participantRole,
  connectionStatus,
  canSendMessages,
}) => {
  const getStatusBadge = () => {
    switch (connectionStatus) {
      case 'SUBSCRIBED':
        return (
          <span className="inline-flex items-center text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200">
            <Wifi className="w-3.5 h-3.5 mr-1" />
            Live
          </span>
        );
      case 'CHANNEL_ERROR':
      case 'TIMED_OUT':
        return (
          <span className="inline-flex items-center text-xs font-semibold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
            <WifiOff className="w-3.5 h-3.5 mr-1" />
            Reconnecting
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center text-xs font-semibold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full">
            <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
            Connecting
          </span>
        );
    }
  };

  return (
    <div className="bg-white border-b border-slate-200 px-4 sm:px-6 py-3.5 flex items-center justify-between shadow-sm">
      <div className="flex items-center space-x-3.5">
        <Link
          to={`/bookings/${bookingId}`}
          className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition"
          title="Back to Booking"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>

        <div>
          <div className="flex items-center space-x-1.5">
            <h2 className="text-sm font-bold text-slate-900 leading-tight">
              {participantName || (participantRole === 'mechanic' ? 'Assigned Mechanic' : 'Customer')}
            </h2>
            {participantRole === 'mechanic' ? (
              <span title="Verified Specialist">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              </span>
            ) : (
              <span title="Vehicle Owner">
                <Wrench className="w-3 h-3 text-slate-400" />
              </span>
            )}
          </div>

          <div className="flex items-center space-x-2 mt-0.5">
            <span className="text-[11px] font-semibold text-emerald-600 uppercase tracking-wider">
              Booking #{bookingNumber || bookingId.slice(0, 8)}
            </span>
            {!canSendMessages && (
              <>
                <span className="text-slate-300">•</span>
                <span className="text-[10px] text-amber-600 font-medium">Read-Only</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div>{getStatusBadge()}</div>
    </div>
  );
};
