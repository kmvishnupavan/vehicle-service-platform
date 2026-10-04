import React from 'react';
import {
  Clock,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  XCircle,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import { PayoutStatus } from '../../types/payout';

interface PayoutStatusBadgeProps {
  status: PayoutStatus | string;
  className?: string;
}

export const PayoutStatusBadge: React.FC<PayoutStatusBadgeProps> = ({
  status,
  className = '',
}) => {
  const normStatus = (status || '').toLowerCase() as PayoutStatus;

  switch (normStatus) {
    case 'paid':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/80 ${className}`}
        >
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          Paid & Settled
        </span>
      );

    case 'eligible':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200/80 ${className}`}
        >
          <Sparkles className="w-3.5 h-3.5 text-blue-600" />
          Eligible
        </span>
      );

    case 'processing':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/80 ${className}`}
        >
          <RefreshCw className="w-3.5 h-3.5 text-indigo-600 animate-spin" />
          Processing
        </span>
      );

    case 'pending':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200/80 ${className}`}
        >
          <Clock className="w-3.5 h-3.5 text-amber-600" />
          Pending Hold
        </span>
      );

    case 'reversed':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200/80 ${className}`}
        >
          <RotateCcw className="w-3.5 h-3.5 text-purple-600" />
          Reversed
        </span>
      );

    case 'failed':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200/80 ${className}`}
        >
          <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
          Failed
        </span>
      );

    case 'cancelled':
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-300 ${className}`}
        >
          <XCircle className="w-3.5 h-3.5 text-slate-500" />
          Cancelled
        </span>
      );

    default:
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200 ${className}`}
        >
          {status}
        </span>
      );
  }
};
