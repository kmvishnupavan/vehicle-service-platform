import React from 'react';
import {
  Wallet,
  CheckCircle2,
  Clock,
  Percent,
  Sparkles,
  RotateCcw,
} from 'lucide-react';
import { PayoutSummary } from '../../types/payout';

interface PayoutSummaryCardsProps {
  summary?: PayoutSummary;
  isLoading?: boolean;
}

export const PayoutSummaryCards: React.FC<PayoutSummaryCardsProps> = ({
  summary,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm animate-pulse"
          >
            <div className="h-4 w-24 bg-slate-200 rounded mb-3" />
            <div className="h-8 w-32 bg-slate-200 rounded mb-2" />
            <div className="h-3 w-40 bg-slate-100 rounded" />
          </div>
        ))}
      </div>
    );
  }

  const formatCurrency = (val?: string) => {
    const num = parseFloat(val || '0.00');
    return `₹${num.toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  };

  return (
    <div className="space-y-4">
      {/* Primary KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Net Mechanic Earnings */}
        <div className="bg-gradient-to-br from-emerald-600 to-teal-700 rounded-xl p-5 text-white shadow-md shadow-emerald-900/10">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-100">
              Total Net Earnings
            </span>
            <div className="p-2 bg-white/10 rounded-lg backdrop-blur-sm">
              <Wallet className="w-5 h-5 text-white" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            {formatCurrency(summary?.total_net)}
          </div>
          <p className="mt-2 text-xs text-emerald-100/90">
            Authoritative net payout after platform commission
          </p>
        </div>

        {/* Cleared & Eligible */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm hover:border-slate-300 transition">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Eligible for Settlement
            </span>
            <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
              <Sparkles className="w-5 h-5" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-extrabold text-blue-700 tracking-tight">
            {formatCurrency(summary?.eligible_amount)}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Cleared funds ready for disbursement batch
          </p>
        </div>

        {/* Paid & Disbursed */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm hover:border-slate-300 transition">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Settled to Bank
            </span>
            <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
              <CheckCircle2 className="w-5 h-5" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-extrabold text-emerald-700 tracking-tight">
            {formatCurrency(summary?.paid_amount)}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Successfully disbursed and settled
          </p>
        </div>

        {/* Pending Clearance */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-sm hover:border-slate-300 transition">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Pending Clearance
            </span>
            <div className="p-2 bg-amber-50 text-amber-600 rounded-lg">
              <Clock className="w-5 h-5" />
            </div>
          </div>
          <div className="text-2xl sm:text-3xl font-extrabold text-amber-700 tracking-tight">
            {formatCurrency(summary?.pending_amount)}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Pending service verification or dispute hold
          </p>
        </div>
      </div>

      {/* Secondary Financial Reconciliation Strip */}
      <div className="bg-slate-50 rounded-xl p-4 border border-slate-200/80 flex flex-wrap items-center justify-between gap-4 text-sm">
        <div className="flex items-center gap-6 flex-wrap">
          <div>
            <span className="text-xs text-slate-500 block">Gross Service Revenue</span>
            <span className="font-semibold text-slate-800">
              {formatCurrency(summary?.total_gross)}
            </span>
          </div>

          <div className="text-slate-300 hidden sm:block">/</div>

          <div className="flex items-center gap-1.5">
            <Percent className="w-4 h-4 text-purple-600" />
            <div>
              <span className="text-xs text-slate-500 block">Platform Commission Retained</span>
              <span className="font-semibold text-purple-700">
                {formatCurrency(summary?.total_commission)}
              </span>
            </div>
          </div>

          {parseFloat(summary?.total_deductions || '0.00') > 0 && (
            <>
              <div className="text-slate-300 hidden sm:block">/</div>
              <div>
                <span className="text-xs text-slate-500 block">Other Deductions</span>
                <span className="font-semibold text-rose-700">
                  {formatCurrency(summary?.total_deductions)}
                </span>
              </div>
            </>
          )}

          {parseFloat(summary?.reversed_amount || '0.00') > 0 && (
            <>
              <div className="text-slate-300 hidden sm:block">/</div>
              <div className="flex items-center gap-1.5">
                <RotateCcw className="w-4 h-4 text-slate-500" />
                <div>
                  <span className="text-xs text-slate-500 block">Reversed / Refunded</span>
                  <span className="font-semibold text-slate-700">
                    {formatCurrency(summary?.reversed_amount)}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="text-xs text-slate-400 font-mono">
          Authoritative Settlement Foundation • Currency: {summary?.currency || 'INR'}
        </div>
      </div>
    </div>
  );
};
