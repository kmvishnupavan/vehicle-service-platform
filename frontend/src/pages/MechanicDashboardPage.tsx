import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Wrench,
  AlertTriangle,
  RotateCcw,
  Star,
  Wallet,
} from 'lucide-react';
import {
  useMechanicDashboardOverview,
  useMechanicPerformance,
  useMechanicEarnings,
  useMechanicRecentJobs,
  useMechanicRecentReviews,
} from '../hooks/useMechanicDashboard';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import {
  IncomingJobOfferCard,
  IncomingJobOffer,
} from '../components/mechanic-dashboard/IncomingJobOfferCard';
import { ServiceExecutionModal } from '../components/mechanic-dashboard/ServiceExecutionModal';
import { RecentJobItem } from '../types/mechanic-dashboard';
import { OverviewCards } from '../components/mechanic-dashboard/OverviewCards';
import { PerformanceSummary } from '../components/mechanic-dashboard/PerformanceSummary';
import { RatingDistribution } from '../components/mechanic-dashboard/RatingDistribution';
import { EarningsSummary } from '../components/mechanic-dashboard/EarningsSummary';
import { RecentJobs } from '../components/mechanic-dashboard/RecentJobs';
import { RecentReviews } from '../components/mechanic-dashboard/RecentReviews';
import { DateFilterBar } from '../components/mechanic-dashboard/DateFilterBar';
import { DateFilterPreset } from '../types/mechanic-dashboard';
import { UpcomingScheduledJobs } from '../components/mechanic-dashboard/UpcomingScheduledJobs';

export const MechanicDashboardPage: React.FC = () => {
  // Date filter state
  const [preset, setPreset] = useState<DateFilterPreset>('all');
  const [fromDate, setFromDate] = useState<string | undefined>(undefined);
  const [toDate, setToDate] = useState<string | undefined>(undefined);

  // Earnings pagination & status state
  const [earningsPage, setEarningsPage] = useState(0);
  const [earningsStatus, setEarningsStatus] = useState('all');
  const earningsPageSize = 10;

  // React Query hooks
  const {
    data: overview,
    isLoading: isOverviewLoading,
    error: overviewError,
    refetch: refetchOverview,
  } = useMechanicDashboardOverview();

  const {
    data: performance,
    isLoading: isPerformanceLoading,
    error: performanceError,
    refetch: refetchPerformance,
  } = useMechanicPerformance({ fromDate, toDate });

  const {
    data: earnings,
    isLoading: isEarningsLoading,
    error: earningsError,
    refetch: refetchEarnings,
  } = useMechanicEarnings({
    fromDate,
    toDate,
    status: earningsStatus,
    limit: earningsPageSize,
    offset: earningsPage * earningsPageSize,
  });

  const {
    data: recentJobs,
    isLoading: isJobsLoading,
    error: jobsError,
    refetch: refetchJobs,
  } = useMechanicRecentJobs(5, 0);

  const {
    data: recentReviews,
    isLoading: isReviewsLoading,
    error: reviewsError,
    refetch: refetchReviews,
  } = useMechanicRecentReviews(5, 0);

  // Poll for real-time incoming job offers dispatched by matching engine
  const { data: pendingOffer, refetch: refetchOffer } = useQuery<IncomingJobOffer | null>({
    queryKey: ['mechanic-pending-offer'],
    queryFn: async () => {
      try {
        const res = await api.get<IncomingJobOffer | null>('/mechanics/pending-offer');
        return res || null;
      } catch {
        return null;
      }
    },
    refetchInterval: 10000,
  });

  const handleAcceptOffer = async (assignmentId: string) => {
    await api.post(`/matching/assignments/${assignmentId}/accept`);
    refetchOffer();
    refetchOverview();
    refetchJobs();
  };

  const handleDeclineOffer = async (assignmentId: string, reason?: string) => {
    await api.post(`/matching/assignments/${assignmentId}/reject`, { reason });
    refetchOffer();
  };

  const [selectedJobForWorkbench, setSelectedJobForWorkbench] = useState<RecentJobItem | null>(null);
  const [isWorkbenchOpen, setIsWorkbenchOpen] = useState(false);

  const handleRecordArrival = async (job: RecentJobItem) => {
    try {
      await api.post(`/bookings/${job.booking_id}/arrive`);
      refetchJobs();
      refetchOverview();
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to record arrival.');
    }
  };

  const handleOpenWorkbench = (job: RecentJobItem) => {
    setSelectedJobForWorkbench(job);
    setIsWorkbenchOpen(true);
  };

  const handleFilterChange = (
    newPreset: DateFilterPreset,
    newFrom?: string,
    newTo?: string
  ) => {
    setPreset(newPreset);
    setFromDate(newFrom);
    setToDate(newTo);
    setEarningsPage(0); // reset pagination when filters change
  };

  const handleRetryAll = () => {
    refetchOverview();
    refetchPerformance();
    refetchEarnings();
    refetchJobs();
    refetchReviews();
    refetchOffer();
  };

  const hasCriticalError =
    overviewError || performanceError || earningsError || jobsError || reviewsError;

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16">
      {/* Top Header Banner */}
      <div className="bg-white border-b border-slate-200/80 sticky top-16 z-20 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center space-x-3.5">
              <div className="w-12 h-12 rounded-2xl bg-emerald-600 text-white flex items-center justify-center shadow-sm">
                <Wrench className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
                    Mechanic Dashboard
                  </h1>
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse" />
                    Available
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Real-time operational metrics, customer reviews & authoritative earnings
                </p>
              </div>
            </div>

            {/* Quick Rating Badge & Payouts Button */}
            <div className="flex items-center space-x-3">
              <Link
                to="/mechanic/payouts"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold shadow-xs transition"
              >
                <Wallet className="w-4 h-4" />
                <span>Payout Ledger</span>
              </Link>

              <div className="bg-slate-50 border border-slate-200/80 rounded-xl px-3.5 py-2 flex items-center space-x-2.5">
                {overview && overview.review_count > 0 ? (
                  <>
                    <div className="flex items-center text-amber-500">
                      <Star className="w-4 h-4 fill-amber-400" />
                      <span className="ml-1 text-sm font-bold text-slate-900">
                        {overview.average_rating.toFixed(1)}
                      </span>
                    </div>
                    <span className="text-slate-300">|</span>
                    <span className="text-xs text-slate-500">
                      {overview.review_count} {overview.review_count === 1 ? 'review' : 'reviews'}
                    </span>
                  </>
                ) : (
                  <span className="text-xs font-medium text-slate-500 italic">
                    No reviews yet
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        {/* API Error State */}
        {hasCriticalError && (
          <div className="mb-8 bg-rose-50 border border-rose-200 rounded-2xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start space-x-3 text-rose-800">
              <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-bold">Failed to load authoritative dashboard data</h4>
                <p className="text-xs text-rose-600 mt-0.5">
                  Please verify network connectivity and ensure you are logged in with an active mechanic account.
                </p>
              </div>
            </div>
            <button
              onClick={handleRetryAll}
              className="inline-flex items-center px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white transition shadow-xs"
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
              Retry Connection
            </button>
          </div>
        )}

        {/* Real-Time Incoming Job Offer Alert */}
        {pendingOffer && (
          <div className="mb-6">
            <IncomingJobOfferCard
              offer={pendingOffer}
              onAccept={handleAcceptOffer}
              onDecline={handleDeclineOffer}
            />
          </div>
        )}

        {/* Date Filter Bar */}
        <DateFilterBar
          currentPreset={preset}
          fromDate={fromDate}
          toDate={toDate}
          onFilterChange={handleFilterChange}
        />

        {/* KPI Overview Cards */}
        <OverviewCards overview={overview} isLoading={isOverviewLoading} />

        {/* Multi-column Grid Layout (Desktop: 2 columns 8/4, Tablet/Mobile responsive) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Main Left Column (8 cols on desktop) */}
          <div className="lg:col-span-8 space-y-8">
            {/* Operational Performance */}
            <PerformanceSummary
              performance={performance}
              isLoading={isPerformanceLoading}
            />

            {/* Earnings Breakdown */}
            <EarningsSummary
              earnings={earnings}
              isLoading={isEarningsLoading}
              page={earningsPage}
              pageSize={earningsPageSize}
              onPageChange={setEarningsPage}
              statusFilter={earningsStatus}
              onStatusFilterChange={(st) => {
                setEarningsStatus(st);
                setEarningsPage(0);
              }}
            />

            {/* Upcoming Scheduled Jobs */}
            <UpcomingScheduledJobs />

            {/* Recent Assigned Jobs */}
            <RecentJobs
              jobs={recentJobs}
              isLoading={isJobsLoading}
              onOpenWorkbench={handleOpenWorkbench}
              onRecordArrival={handleRecordArrival}
            />
          </div>

          {/* Right Sidebar Column (4 cols on desktop) */}
          <div className="lg:col-span-4 space-y-8">
            {/* Rating Distribution */}
            <RatingDistribution
              distribution={performance?.rating_distribution || {}}
              reviewCount={performance?.review_count ?? overview?.review_count ?? 0}
              averageRating={performance?.average_rating ?? overview?.average_rating ?? 0}
              isLoading={isPerformanceLoading || isOverviewLoading}
            />

            {/* Recent Customer Reviews */}
            <RecentReviews reviews={recentReviews} isLoading={isReviewsLoading} />
          </div>
        </div>
      </div>

      {/* Service Execution Workbench Modal */}
      {selectedJobForWorkbench && (
        <ServiceExecutionModal
          isOpen={isWorkbenchOpen}
          onClose={() => setIsWorkbenchOpen(false)}
          bookingId={selectedJobForWorkbench.booking_id}
          bookingNumber={selectedJobForWorkbench.booking_number}
          bookingStatus={selectedJobForWorkbench.booking_status}
          onRefresh={() => {
            refetchJobs();
            refetchOverview();
          }}
        />
      )}
    </div>
  );
};
