import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Wallet,
  ArrowLeft,
  AlertTriangle,
  RotateCcw,
  ShieldCheck,
  Building2,
} from 'lucide-react';
import {
  useMechanicPayoutSummary,
  useMechanicPayouts,
} from '../hooks/useMechanicPayouts';
import { PayoutSummaryCards } from '../components/mechanic-payouts/PayoutSummaryCards';
import {
  PayoutFilters,
  PayoutStatusFilter,
  DatePreset,
} from '../components/mechanic-payouts/PayoutFilters';
import { PayoutTable } from '../components/mechanic-payouts/PayoutTable';

export const MechanicPayoutsPage: React.FC = () => {
  // Filter states
  const [selectedStatus, setSelectedStatus] = useState<PayoutStatusFilter>('all');
  const [selectedPreset, setSelectedPreset] = useState<DatePreset>('all');
  const [fromDate, setFromDate] = useState<string | undefined>(undefined);
  const [toDate, setToDate] = useState<string | undefined>(undefined);

  // Pagination state
  const [offset, setOffset] = useState<number>(0);
  const limit = 10;

  // React Query hooks
  const {
    data: summary,
    isLoading: isSummaryLoading,
    error: summaryError,
    refetch: refetchSummary,
  } = useMechanicPayoutSummary();

  const {
    data: payoutData,
    isLoading: isPayoutsLoading,
    error: payoutsError,
    refetch: refetchPayouts,
  } = useMechanicPayouts({
    status: selectedStatus,
    fromDate,
    toDate,
    limit,
    offset,
  });

  const handleStatusChange = (status: PayoutStatusFilter) => {
    setSelectedStatus(status);
    setOffset(0);
  };

  const handleDateChange = (preset: DatePreset, from?: string, to?: string) => {
    setSelectedPreset(preset);
    setFromDate(from);
    setToDate(to);
    setOffset(0);
  };

  const handleRefresh = () => {
    refetchSummary();
    refetchPayouts();
  };

  const hasError = summaryError || payoutsError;

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16">
      {/* Header Banner */}
      <div className="bg-white border-b border-slate-200/80 sticky top-16 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Link
                  to="/mechanic/dashboard"
                  className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-emerald-600 transition"
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" />
                  Dashboard
                </Link>
                <span className="text-slate-300">/</span>
                <span className="text-xs font-semibold text-emerald-600">
                  Payouts & Settlement
                </span>
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                <div className="p-2 bg-emerald-100/70 text-emerald-700 rounded-lg">
                  <Wallet className="w-6 h-6" />
                </div>
                <span>Mechanic Payout Ledger</span>
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="hidden sm:flex items-center gap-2 text-xs font-medium text-slate-500 bg-slate-100/70 px-3 py-2 rounded-lg border border-slate-200/60">
                <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>Authoritative Settlement Ledger</span>
              </div>
              <Link
                to="/mechanic/payout-account"
                className="inline-flex items-center gap-2 px-3.5 py-2 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 shadow-sm transition"
              >
                <Building2 className="w-4 h-4" />
                <span>Bank Account & Onboarding</span>
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {/* Error Alert */}
        {hasError && (
          <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
              <div>
                <h4 className="text-sm font-bold text-rose-900">Failed to load payout data</h4>
                <p className="text-xs text-rose-700">
                  Please verify your network connection or try refreshing the ledger.
                </p>
              </div>
            </div>
            <button
              onClick={handleRefresh}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-medium hover:bg-rose-700 transition"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Retry
            </button>
          </div>
        )}

        {/* 1. Summary Cards */}
        <section aria-label="Payout Summary">
          <PayoutSummaryCards
            summary={summary}
            isLoading={isSummaryLoading}
          />
        </section>

        {/* 2. Filters */}
        <section aria-label="Payout Filters">
          <PayoutFilters
            selectedStatus={selectedStatus}
            onStatusChange={handleStatusChange}
            selectedPreset={selectedPreset}
            fromDate={fromDate}
            toDate={toDate}
            onDateChange={handleDateChange}
            onRefresh={handleRefresh}
            isLoading={isPayoutsLoading || isSummaryLoading}
          />
        </section>

        {/* 3. Authoritative Payout Table */}
        <section aria-label="Payout History">
          <PayoutTable
            items={payoutData?.items || []}
            total={payoutData?.total || 0}
            limit={limit}
            offset={offset}
            onPageChange={setOffset}
            isLoading={isPayoutsLoading}
          />
        </section>
      </div>
    </div>
  );
};
