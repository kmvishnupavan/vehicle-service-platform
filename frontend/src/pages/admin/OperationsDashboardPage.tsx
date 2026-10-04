import React, { useState } from 'react';
import {
  Activity,
  ShieldCheck,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  Radio,
  FileSearch,
  Compass,
  Play,
  Calendar,
  Sliders,
  BarChart3,
  MapPin,
  Check,
  Server,
  Zap,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  useOperationsStats,
  useReconciliationReport,
} from '../../hooks/useAdminOperations';
import {
  useOperationalMetrics,
  useBackgroundJobHistory,
  useTriggerBackgroundJobs,
  useLocationAnomalies,
  useMatchingPolicies,
  useActivateMatchingPolicy,
  useAdminScheduledBookings,
} from '../../hooks/useOperationalAutomation';
import {
  DEFAULT_OPERATIONAL_THRESHOLDS,
  OperationalAlertThresholds,
} from '../../types/operationalAutomation';

type TabType = 'health' | 'metrics' | 'scheduled' | 'anomalies' | 'policies' | 'reconciliation';

export const OperationsDashboardPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>('health');

  // Existing reconciliation subsystem state
  const [selectedSubsystem, setSelectedSubsystem] = useState<
    'payments' | 'payouts' | 'settlements' | 'webhooks'
  >('payments');

  // Scheduled bookings filter
  const [scheduledStatusFilter, setScheduledStatusFilter] = useState<string>('all');

  // Configurable alert thresholds state
  const [thresholds, setThresholds] = useState<OperationalAlertThresholds>(
    DEFAULT_OPERATIONAL_THRESHOLDS
  );

  // Background job execution feedback
  const [jobTriggerFeedback, setJobTriggerFeedback] = useState<string | null>(null);

  // Queries
  const {
    data: stats,
    isLoading: isStatsLoading,
    error: statsError,
    refetch: refetchStats,
  } = useOperationsStats();

  const {
    data: reconReport,
    isLoading: isReconLoading,
    refetch: refetchRecon,
  } = useReconciliationReport(selectedSubsystem);

  const {
    data: opMetrics,
    isLoading: isMetricsLoading,
    refetch: refetchMetrics,
  } = useOperationalMetrics();

  const {
    data: jobHistory,
    isLoading: isJobsLoading,
    refetch: refetchJobs,
  } = useBackgroundJobHistory(20);

  const {
    data: anomalies,
    isLoading: isAnomaliesLoading,
    refetch: refetchAnomalies,
  } = useLocationAnomalies(30);

  const {
    data: policies,
    isLoading: isPoliciesLoading,
    refetch: refetchPolicies,
  } = useMatchingPolicies();

  const {
    data: scheduledBookings,
    isLoading: isScheduledLoading,
    refetch: refetchScheduled,
  } = useAdminScheduledBookings(
    scheduledStatusFilter === 'all' ? undefined : scheduledStatusFilter
  );

  // Mutations
  const { mutateAsync: triggerJobs, isPending: isTriggeringJobs } = useTriggerBackgroundJobs();
  const { mutateAsync: activatePolicy, isPending: isActivatingPolicy } = useActivateMatchingPolicy();

  const handleRefreshAll = () => {
    refetchStats();
    refetchRecon();
    refetchMetrics();
    refetchJobs();
    refetchAnomalies();
    refetchPolicies();
    refetchScheduled();
  };

  const handleRunJobs = async (jobNames?: string[]) => {
    setJobTriggerFeedback(null);
    try {
      const res = await triggerJobs(jobNames);
      setJobTriggerFeedback(`Successfully executed ${res.length} background jobs.`);
      setTimeout(() => setJobTriggerFeedback(null), 5000);
    } catch (err: any) {
      setJobTriggerFeedback(`Failed to run background jobs: ${err?.message || 'Error'}`);
    }
  };

  const handleActivatePolicy = async (version: string) => {
    if (!window.confirm(`Activate matching policy ${version}? This will deactivate all other versions.`)) {
      return;
    }
    try {
      await activatePolicy(version);
      refetchPolicies();
    } catch (err: any) {
      alert(`Failed to activate policy: ${err?.message || 'Error'}`);
    }
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'bg-rose-100 text-rose-800 border-rose-300';
      case 'high':
        return 'bg-orange-100 text-orange-800 border-orange-300';
      case 'medium':
        return 'bg-amber-100 text-amber-800 border-amber-300';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const metricsData = opMetrics?.metrics;

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16">
      {/* Top Banner */}
      <div className="bg-white border-b border-slate-200/80 sticky top-16 z-10 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-1">
                <span>Administration</span>
                <span className="text-slate-300">/</span>
                <span className="text-indigo-600">Operations & Reliability (Phase 13)</span>
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                <div className="p-2 bg-indigo-100/70 text-indigo-700 rounded-xl">
                  <Activity className="w-6 h-6" />
                </div>
                <span>Operations & Reliability Center</span>
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {stats?.safety_guard && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-xs font-bold">
                  <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  <span>{stats.safety_guard.real_money_movement}</span>
                </div>
              )}

              <Link
                to="/admin/matching"
                className="inline-flex items-center gap-1.5 px-3 py-2 bg-white text-indigo-700 border border-indigo-200 rounded-xl text-xs font-semibold hover:bg-indigo-50 shadow-xs transition"
              >
                <Compass className="w-4 h-4 text-indigo-600" />
                <span>Matching Live</span>
              </Link>

              <Link
                to="/admin/audit-logs"
                className="inline-flex items-center gap-1.5 px-3 py-2 bg-white text-slate-700 border border-slate-300 rounded-xl text-xs font-semibold hover:bg-slate-50 shadow-xs transition"
              >
                <FileSearch className="w-4 h-4 text-slate-500" />
                <span>Audit Logs</span>
              </Link>

              <button
                type="button"
                onClick={handleRefreshAll}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 shadow-xs transition"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Refresh Probes</span>
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-1 overflow-x-auto pt-4 mt-2 border-t border-slate-100 text-xs font-semibold">
            {[
              { id: 'health', label: 'System Health & Jobs', icon: Server },
              { id: 'metrics', label: 'Operational KPIs & Alerts', icon: BarChart3 },
              { id: 'scheduled', label: 'Scheduled Bookings', icon: Calendar },
              { id: 'anomalies', label: 'Location Reliability', icon: MapPin },
              { id: 'policies', label: 'Matching Policies', icon: Sliders },
              { id: 'reconciliation', label: 'Reconciliation Engine', icon: ShieldCheck },
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as TabType)}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl transition shrink-0 ${
                    activeTab === tab.id
                      ? 'bg-indigo-50 text-indigo-700 font-bold border border-indigo-200/80 shadow-xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {/* =====================================================================
            TAB 1: SYSTEM HEALTH & BACKGROUND JOBS
           ===================================================================== */}
        {activeTab === 'health' && (
          <div className="space-y-6">
            {isStatsLoading ? (
              <div className="p-8 text-center text-slate-500 text-xs bg-white rounded-2xl border border-slate-200 shadow-xs">
                <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                Loading system readiness probes...
              </div>
            ) : statsError ? (
              <div className="p-4 bg-rose-50 border border-rose-200 rounded-2xl text-xs text-rose-700 font-semibold">
                Failed to load system readiness probes.
              </div>
            ) : stats && (
              <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-emerald-50 text-emerald-600 rounded-xl">
                      <Radio className="w-5 h-5 animate-pulse" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">
                        System Readiness: {stats.system_health.status.toUpperCase()}
                      </h3>
                      <p className="text-xs text-slate-500">
                        Environment: <span className="font-semibold text-slate-700 uppercase">{stats.environment}</span> | Probe Time: {new Date(stats.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {Object.entries(stats.system_health.checks || {}).map(([key, val]) => (
                      <span
                        key={key}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-100 text-slate-700 border border-slate-200"
                      >
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        <span className="capitalize">{key}:</span>
                        <span className="font-bold text-slate-900">{val}</span>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Operational Lifecycle Breakdown Cards */}
            {stats && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Bookings Card */}
                <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase tracking-wider">
                    <span>Bookings Lifecycle</span>
                    <Layers className="w-4 h-4 text-indigo-500" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">In Service</span>
                      <span className="text-base font-extrabold text-indigo-700">{stats.bookings_breakdown.in_service || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Assigned</span>
                      <span className="text-base font-extrabold text-slate-800">{stats.bookings_breakdown.assigned || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Completed</span>
                      <span className="text-base font-extrabold text-emerald-700">{stats.bookings_breakdown.completed || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Cancelled</span>
                      <span className="text-base font-extrabold text-slate-600">{stats.bookings_breakdown.cancelled || 0}</span>
                    </div>
                  </div>
                </div>

                {/* Payments Card */}
                <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase tracking-wider">
                    <span>Payment Gateways</span>
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Captured</span>
                      <span className="text-base font-extrabold text-emerald-700">{stats.payments_breakdown.captured || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Pending</span>
                      <span className="text-base font-extrabold text-amber-700">{stats.payments_breakdown.pending || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Failed</span>
                      <span className="text-base font-extrabold text-rose-700">{stats.payments_breakdown.failed || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Refunded</span>
                      <span className="text-base font-extrabold text-purple-700">{stats.payments_breakdown.refunded || 0}</span>
                    </div>
                  </div>
                </div>

                {/* Payouts Card */}
                <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase tracking-wider">
                    <span>Mechanic Payouts</span>
                    <Clock className="w-4 h-4 text-amber-500" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Paid/Settled</span>
                      <span className="text-base font-extrabold text-emerald-700">{stats.payouts_breakdown.paid || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Processing</span>
                      <span className="text-base font-extrabold text-indigo-700">{stats.payouts_breakdown.processing || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Approval Req.</span>
                      <span className="text-base font-extrabold text-amber-700">{stats.payouts_breakdown.approval_required || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Eligible</span>
                      <span className="text-base font-extrabold text-slate-800">{stats.payouts_breakdown.eligible || 0}</span>
                    </div>
                  </div>
                </div>

                {/* Webhooks Card */}
                <div className="bg-white p-5 rounded-2xl border border-slate-200/80 shadow-xs space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase tracking-wider">
                    <span>Webhook Ingress</span>
                    <Activity className="w-4 h-4 text-sky-500" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Processed</span>
                      <span className="text-base font-extrabold text-emerald-700">{stats.webhooks_breakdown.processed || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">In-Flight</span>
                      <span className="text-base font-extrabold text-indigo-700">{stats.webhooks_breakdown.processing || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Failed</span>
                      <span className="text-base font-extrabold text-rose-700">{stats.webhooks_breakdown.failed || 0}</span>
                    </div>
                    <div className="bg-slate-50 p-2 rounded-lg">
                      <span className="text-slate-400 block text-[10px]">Notifications</span>
                      <span className="text-base font-extrabold text-slate-800">{stats.notifications_breakdown.sent || 0}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Background Job Runner & Execution Audit */}
            <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
              <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-500" />
                    <span>Automated Background Job Runner</span>
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Distributed locking via PostgreSQL advisory locks ensures zero concurrent collision across worker nodes.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleRunJobs()}
                    disabled={isTriggeringJobs}
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-xs transition disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>{isTriggeringJobs ? 'Running All Jobs...' : 'Trigger All Jobs Now'}</span>
                  </button>
                </div>
              </div>

              {jobTriggerFeedback && (
                <div className="px-5 py-3 bg-indigo-50 border-b border-indigo-100 text-xs font-semibold text-indigo-800 flex items-center justify-between">
                  <span>{jobTriggerFeedback}</span>
                  <button onClick={() => setJobTriggerFeedback(null)} className="text-indigo-500 hover:text-indigo-700">✕</button>
                </div>
              )}

              {isJobsLoading ? (
                <div className="p-12 text-center text-slate-500 text-xs">
                  <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                  Loading background job audit trail...
                </div>
              ) : !jobHistory || jobHistory.length === 0 ? (
                <div className="p-10 text-center text-slate-500 text-xs">
                  No background jobs have executed yet. Click &quot;Trigger All Jobs Now&quot; to execute.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                        <th className="py-3 px-5">Job Name</th>
                        <th className="py-3 px-5">Status</th>
                        <th className="py-3 px-5">Processed</th>
                        <th className="py-3 px-5">Succeeded</th>
                        <th className="py-3 px-5">Failed</th>
                        <th className="py-3 px-5">Execution ID</th>
                        <th className="py-3 px-5 text-right">Started At</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {jobHistory.map((job) => (
                        <tr key={job.id} className="hover:bg-slate-50/60 transition">
                          <td className="py-3 px-5 font-bold text-slate-900 font-mono">
                            {job.job_name}
                          </td>
                          <td className="py-3 px-5">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                job.status === 'completed'
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : job.status === 'running'
                                  ? 'bg-blue-100 text-blue-800 animate-pulse'
                                  : 'bg-rose-100 text-rose-800'
                              }`}
                            >
                              {job.status.toUpperCase()}
                            </span>
                          </td>
                          <td className="py-3 px-5 font-semibold text-slate-700">
                            {job.records_processed}
                          </td>
                          <td className="py-3 px-5 text-emerald-600 font-semibold">
                            {job.records_succeeded}
                          </td>
                          <td className="py-3 px-5 text-rose-600 font-semibold">
                            {job.records_failed}
                          </td>
                          <td className="py-3 px-5 font-mono text-[10px] text-slate-400">
                            {job.execution_id.slice(0, 16)}...
                          </td>
                          <td className="py-3 px-5 text-right text-slate-500 text-[11px]">
                            {new Date(job.started_at).toLocaleTimeString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* =====================================================================
            TAB 2: OPERATIONAL KPIS & CONFIGURABLE ALERT THRESHOLDS
           ===================================================================== */}
        {activeTab === 'metrics' && (
          <div className="space-y-6">
            {isMetricsLoading ? (
              <div className="p-12 text-center text-slate-500 text-xs bg-white rounded-2xl border border-slate-200">
                <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                Aggregating platform metrics...
              </div>
            ) : metricsData ? (
              <>
                {/* Real-time KPI Metric Cards */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Matching Exhaustion */}
                  <div className={`p-5 rounded-2xl border shadow-xs space-y-2 ${
                    metricsData.matching_exhaustion_rate > thresholds.matching_exhaustion_rate
                      ? 'bg-rose-50 border-rose-200 text-rose-900'
                      : 'bg-white border-slate-200/80 text-slate-900'
                  }`}>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase">
                      <span>Matching Exhaustion</span>
                      <Compass className="w-4 h-4 text-indigo-500" />
                    </div>
                    <div className="text-2xl font-extrabold">
                      {(metricsData.matching_exhaustion_rate * 100).toFixed(1)}%
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Threshold: {(thresholds.matching_exhaustion_rate * 100).toFixed(1)}% | Acceptance: {(metricsData.offer_acceptance_rate * 100).toFixed(1)}%
                    </p>
                  </div>

                  {/* Dynamic Road ETA & Fallback */}
                  <div className={`p-5 rounded-2xl border shadow-xs space-y-2 ${
                    metricsData.routing_failure_rate > thresholds.routing_failure_rate
                      ? 'bg-rose-50 border-rose-200 text-rose-900'
                      : 'bg-white border-slate-200/80 text-slate-900'
                  }`}>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase">
                      <span>Avg Road ETA / Routing</span>
                      <Clock className="w-4 h-4 text-emerald-500" />
                    </div>
                    <div className="text-2xl font-extrabold">
                      {metricsData.average_eta_minutes.toFixed(1)} min
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Fallback Rate: {(metricsData.routing_fallback_rate * 100).toFixed(1)}% | Failures: {(metricsData.routing_failure_rate * 100).toFixed(1)}%
                    </p>
                  </div>

                  {/* Location Freshness & Anomalies */}
                  <div className={`p-5 rounded-2xl border shadow-xs space-y-2 ${
                    metricsData.stale_location_rate > thresholds.stale_location_rate
                      ? 'bg-amber-50 border-amber-200 text-amber-900'
                      : 'bg-white border-slate-200/80 text-slate-900'
                  }`}>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase">
                      <span>Location Stale Rate</span>
                      <MapPin className="w-4 h-4 text-amber-500" />
                    </div>
                    <div className="text-2xl font-extrabold">
                      {(metricsData.stale_location_rate * 100).toFixed(1)}%
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Detected GPS Anomalies: <span className="font-bold text-rose-600">{metricsData.location_anomaly_count}</span>
                    </p>
                  </div>

                  {/* Notifications Queue Health */}
                  <div className={`p-5 rounded-2xl border shadow-xs space-y-2 ${
                    metricsData.notification_failure_rate > thresholds.notification_failure_rate
                      ? 'bg-rose-50 border-rose-200 text-rose-900'
                      : 'bg-white border-slate-200/80 text-slate-900'
                  }`}>
                    <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase">
                      <span>Notification Failure</span>
                      <Radio className="w-4 h-4 text-sky-500" />
                    </div>
                    <div className="text-2xl font-extrabold">
                      {(metricsData.notification_failure_rate * 100).toFixed(2)}%
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Exponential backoff retry queue handles transient network failures.
                    </p>
                  </div>
                </div>

                {/* Configurable Operational Alert Thresholds Panel */}
                <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs space-y-5">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                    <div>
                      <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                        <Sliders className="w-4 h-4 text-indigo-600" />
                        <span>Configurable Operational Alert Thresholds</span>
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Tune platform operational alert sensitivities dynamically without modifying codebase constants.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setThresholds(DEFAULT_OPERATIONAL_THRESHOLDS)}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition"
                    >
                      Reset to Defaults
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5 text-xs">
                    {/* Matching Exhaustion Slider */}
                    <div className="space-y-1.5 p-4 rounded-xl bg-slate-50 border border-slate-200">
                      <div className="flex justify-between font-bold text-slate-700">
                        <span>Matching Exhaustion Limit:</span>
                        <span className="text-indigo-600">{(thresholds.matching_exhaustion_rate * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min="2"
                        max="30"
                        value={thresholds.matching_exhaustion_rate * 100}
                        onChange={(e) =>
                          setThresholds((prev) => ({
                            ...prev,
                            matching_exhaustion_rate: parseFloat(e.target.value) / 100,
                          }))
                        }
                        className="w-full text-indigo-600"
                      />
                    </div>

                    {/* Stale Location Limit */}
                    <div className="space-y-1.5 p-4 rounded-xl bg-slate-50 border border-slate-200">
                      <div className="flex justify-between font-bold text-slate-700">
                        <span>Stale Location Limit:</span>
                        <span className="text-amber-600">{(thresholds.stale_location_rate * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="20"
                        value={thresholds.stale_location_rate * 100}
                        onChange={(e) =>
                          setThresholds((prev) => ({
                            ...prev,
                            stale_location_rate: parseFloat(e.target.value) / 100,
                          }))
                        }
                        className="w-full text-amber-600"
                      />
                    </div>

                    {/* Routing Failure Limit */}
                    <div className="space-y-1.5 p-4 rounded-xl bg-slate-50 border border-slate-200">
                      <div className="flex justify-between font-bold text-slate-700">
                        <span>Routing Failure Limit:</span>
                        <span className="text-rose-600">{(thresholds.routing_failure_rate * 100).toFixed(0)}%</span>
                      </div>
                      <input
                        type="range"
                        min="1"
                        max="15"
                        value={thresholds.routing_failure_rate * 100}
                        onChange={(e) =>
                          setThresholds((prev) => ({
                            ...prev,
                            routing_failure_rate: parseFloat(e.target.value) / 100,
                          }))
                        }
                        className="w-full text-rose-600"
                      />
                    </div>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        )}

        {/* =====================================================================
            TAB 3: SCHEDULED BOOKINGS MONITORING
           ===================================================================== */}
        {activeTab === 'scheduled' && (
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden space-y-4">
            <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-emerald-600" />
                  <span>Scheduled Booking Monitoring & Dispatch Pipeline</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Advance service windows, automatic 30-minute dispatch triggers, and cancellation states.
                </p>
              </div>

              {/* Status Filter */}
              <div className="flex items-center gap-1.5 bg-slate-100/80 p-1 rounded-xl text-xs font-semibold">
                {['all', 'scheduled', 'dispatching', 'dispatched', 'cancelled', 'failed'].map((st) => (
                  <button
                    key={st}
                    onClick={() => setScheduledStatusFilter(st)}
                    className={`px-3 py-1.5 rounded-lg capitalize transition ${
                      scheduledStatusFilter === st
                        ? 'bg-white text-slate-900 shadow-xs font-bold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>

            {isScheduledLoading ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                Loading scheduled bookings...
              </div>
            ) : !scheduledBookings || scheduledBookings.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                No scheduled bookings found for status &quot;{scheduledStatusFilter}&quot;.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                      <th className="py-3 px-5">Booking ID</th>
                      <th className="py-3 px-5">Scheduled Window</th>
                      <th className="py-3 px-5">Timezone</th>
                      <th className="py-3 px-5">Dispatch Time</th>
                      <th className="py-3 px-5">Status</th>
                      <th className="py-3 px-5">Attempts</th>
                      <th className="py-3 px-5 text-right">Created</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {scheduledBookings.map((b) => (
                      <tr key={b.id} className="hover:bg-slate-50/60 transition">
                        <td className="py-3 px-5 font-mono text-[11px] font-bold text-slate-800">
                          {b.booking_id.slice(0, 8)}...
                        </td>
                        <td className="py-3 px-5 font-medium text-slate-800">
                          {new Date(b.scheduled_start_at).toLocaleString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}{' '}
                          -{' '}
                          {new Date(b.scheduled_end_at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </td>
                        <td className="py-3 px-5 text-slate-600">{b.timezone}</td>
                        <td className="py-3 px-5 text-slate-600">
                          {new Date(b.dispatch_at).toLocaleTimeString()}
                        </td>
                        <td className="py-3 px-5">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold capitalize ${
                              b.status === 'scheduled'
                                ? 'bg-indigo-100 text-indigo-800'
                                : b.status === 'dispatched'
                                ? 'bg-emerald-100 text-emerald-800'
                                : b.status === 'cancelled'
                                ? 'bg-slate-100 text-slate-700'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            {b.status}
                          </span>
                        </td>
                        <td className="py-3 px-5 font-semibold text-slate-700">{b.attempt_count}</td>
                        <td className="py-3 px-5 text-right text-slate-500 text-[11px]">
                          {new Date(b.created_at).toLocaleDateString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* =====================================================================
            TAB 4: LOCATION RELIABILITY & GPS ANOMALIES
           ===================================================================== */}
        {activeTab === 'anomalies' && (
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden space-y-4">
            <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-rose-600" />
                  <span>Mechanic GPS Anomaly & Heartbeat Reliability Ledger</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Impossible speed violations (&gt;160 km/h), large teleportation jumps, and stale location tracking.
                </p>
              </div>
            </div>

            {isAnomaliesLoading ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                Auditing GPS coordinates...
              </div>
            ) : !anomalies || anomalies.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                <p className="font-semibold text-slate-800">Zero GPS anomalies detected</p>
                <p className="text-slate-400 mt-0.5">All active mechanics report valid speeds, coordinates, and fresh heartbeats.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                      <th className="py-3 px-5">Mechanic ID</th>
                      <th className="py-3 px-5">Anomaly Type</th>
                      <th className="py-3 px-5">Severity</th>
                      <th className="py-3 px-5">Status</th>
                      <th className="py-3 px-5">Details</th>
                      <th className="py-3 px-5 text-right">Detected At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {anomalies.map((a) => (
                      <tr key={a.id} className="hover:bg-slate-50/60 transition">
                        <td className="py-3 px-5 font-mono text-[11px] text-slate-700">
                          {a.mechanic_id.slice(0, 8)}...
                        </td>
                        <td className="py-3 px-5 font-semibold text-slate-900">
                          {a.anomaly_type.replace(/_/g, ' ')}
                        </td>
                        <td className="py-3 px-5">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${getSeverityBadge(a.severity)}`}>
                            {a.severity.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-3 px-5 font-medium text-slate-600 capitalize">{a.status}</td>
                        <td className="py-3 px-5 text-slate-500 text-[11px]">{a.description || 'Speed or distance threshold exceeded'}</td>
                        <td className="py-3 px-5 text-right text-slate-500 text-[11px]">
                          {new Date(a.detected_at).toLocaleTimeString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* =====================================================================
            TAB 5: VERSIONED MATCHING POLICIES
           ===================================================================== */}
        {activeTab === 'policies' && (
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden space-y-4">
            <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Sliders className="w-4 h-4 text-indigo-600" />
                  <span>Versioned Matching Policies</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Dynamic weight governance for proximity, rating, availability, reliability, workload, and acceptance (sum = 1.000).
                </p>
              </div>
            </div>

            {isPoliciesLoading ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                Loading matching policies...
              </div>
            ) : !policies || policies.length === 0 ? (
              <div className="p-10 text-center text-slate-500 text-xs">
                No matching policies found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                      <th className="py-3 px-5">Version</th>
                      <th className="py-3 px-5">Description</th>
                      <th className="py-3 px-5">Proximity</th>
                      <th className="py-3 px-5">Rating</th>
                      <th className="py-3 px-5">Availability</th>
                      <th className="py-3 px-5">Reliability</th>
                      <th className="py-3 px-5">Workload</th>
                      <th className="py-3 px-5">Status</th>
                      <th className="py-3 px-5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {policies.map((p) => (
                      <tr key={p.policy_version} className="hover:bg-slate-50/60 transition">
                        <td className="py-3 px-5 font-bold text-indigo-700">{p.policy_version}</td>
                        <td className="py-3 px-5 text-slate-600">{p.description}</td>
                        <td className="py-3 px-5 font-mono">{(p.proximity_weight * 100).toFixed(0)}%</td>
                        <td className="py-3 px-5 font-mono">{(p.rating_weight * 100).toFixed(0)}%</td>
                        <td className="py-3 px-5 font-mono">{(p.availability_weight * 100).toFixed(0)}%</td>
                        <td className="py-3 px-5 font-mono">{(p.reliability_weight * 100).toFixed(0)}%</td>
                        <td className="py-3 px-5 font-mono">{(p.workload_weight * 100).toFixed(0)}%</td>
                        <td className="py-3 px-5">
                          {p.is_active ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                              <Check className="w-3 h-3 mr-1" />
                              ACTIVE
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600">
                              INACTIVE
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-5 text-right">
                          {!p.is_active && (
                            <button
                              type="button"
                              onClick={() => handleActivatePolicy(p.policy_version)}
                              disabled={isActivatingPolicy}
                              className="px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-xs transition disabled:opacity-50"
                            >
                              Activate
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* =====================================================================
            TAB 6: RECONCILIATION ENGINE (PRESERVED INTACT)
           ===================================================================== */}
        {activeTab === 'reconciliation' && (
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-xs overflow-hidden">
            <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>Automated Discrepancy & Reconciliation Engine</span>
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Continuously checks internal database state against payment and banking providers.
                </p>
              </div>

              {/* Subsystem Select Tabs */}
              <div className="flex items-center gap-1.5 bg-slate-100/80 p-1 rounded-xl">
                {[
                  { id: 'payments', label: 'Payments' },
                  { id: 'payouts', label: 'Payouts' },
                  { id: 'settlements', label: 'Settlement Batches' },
                  { id: 'webhooks', label: 'Webhooks' },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setSelectedSubsystem(tab.id as any)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
                      selectedSubsystem === tab.id
                        ? 'bg-white text-slate-900 shadow-xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Reconciliation Table */}
            {isReconLoading ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                Scanning {selectedSubsystem} for discrepancies...
              </div>
            ) : !reconReport || reconReport.discrepancies.length === 0 ? (
              <div className="p-12 text-center">
                <div className="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-2xl flex items-center justify-center mx-auto mb-3">
                  <CheckCircle2 className="w-6 h-6" />
                </div>
                <h4 className="text-sm font-bold text-slate-800">
                  All {selectedSubsystem.toUpperCase()} Reconciled
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                  Zero discrepancies or financial anomalies detected. Records match expected state machine invariants.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                      <th className="py-3.5 px-6">Discrepancy Type</th>
                      <th className="py-3.5 px-6">Entity / ID</th>
                      <th className="py-3.5 px-6">Internal Status</th>
                      <th className="py-3.5 px-6">Provider Status</th>
                      <th className="py-3.5 px-6">Severity</th>
                      <th className="py-3.5 px-6 text-right">Detected</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-xs">
                    {reconReport.discrepancies.map((d, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/60 transition">
                        <td className="py-4 px-6 font-semibold text-slate-900 flex items-center gap-2">
                          <AlertTriangle className="w-4 h-4 text-amber-500" />
                          <span>{d.discrepancy_type.replace(/_/g, ' ')}</span>
                        </td>
                        <td className="py-4 px-6 font-mono text-[11px] text-slate-600">
                          {d.entity_id ? `${String(d.entity_id).slice(0, 8)}...` : '—'}
                        </td>
                        <td className="py-4 px-6 font-medium text-slate-700">
                          {d.internal_status || '—'}
                        </td>
                        <td className="py-4 px-6 font-medium text-slate-700">
                          {d.provider_status || '—'}
                        </td>
                        <td className="py-4 px-6">
                          <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${getSeverityBadge(d.severity)}`}>
                            {d.severity.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-4 px-6 text-right text-slate-500 text-[11px]">
                          {new Date(d.detected_at).toLocaleTimeString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
