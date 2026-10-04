import React from 'react';
import { Wrench, Calendar, Car } from 'lucide-react';
import { RecentJobsList, RecentJobItem } from '../../types/mechanic-dashboard';

interface RecentJobsProps {
  jobs?: RecentJobsList;
  isLoading: boolean;
  onOpenWorkbench?: (job: RecentJobItem) => void;
  onRecordArrival?: (job: RecentJobItem) => void;
}

export const RecentJobs: React.FC<RecentJobsProps> = ({
  jobs,
  isLoading,
  onOpenWorkbench,
  onRecordArrival,
}) => {
  const getBookingStatusBadge = (status: string) => {
    switch (status) {
      case 'paid':
      case 'service_completed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
            Completed
          </span>
        );
      case 'service_in_progress':
      case 'mechanic_assigned':
      case 'mechanic_en_route':
      case 'mechanic_arrived':
      case 'inspection':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
            In Progress
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800">
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 capitalize">
            {status.replace(/_/g, ' ')}
          </span>
        );
    }
  };

  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm animate-pulse space-y-4">
        <div className="w-32 h-6 bg-slate-200 rounded" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-14 bg-slate-100 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const items = jobs?.items || [];

  return (
    <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <Wrench className="w-5 h-5 text-emerald-600" />
            <span>Recent Assigned Jobs</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Operational activity and dispatched requests
          </p>
        </div>
        <span className="text-xs font-semibold text-slate-500">
          Showing latest {items.length}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="py-10 text-center text-slate-400 space-y-2">
          <Car className="w-8 h-8 text-slate-300 mx-auto" />
          <p className="text-sm font-medium">No assigned jobs found</p>
          <p className="text-xs text-slate-400">
            Newly offered and accepted assignments will be displayed here.
          </p>
        </div>
      ) : (
        <div className="divide-y divide-slate-100">
          {items.map((job: RecentJobItem) => (
            <div
              key={job.booking_id}
              className="py-3.5 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 hover:bg-slate-50/50 p-2 rounded-xl transition"
            >
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold text-slate-900">
                    {job.booking_number}
                  </span>
                  {getBookingStatusBadge(job.booking_status)}
                </div>
                <div className="flex items-center space-x-4 text-xs text-slate-500">
                  <span className="flex items-center">
                    <Car className="w-3.5 h-3.5 mr-1 text-slate-400" />
                    {job.vehicle_summary}
                  </span>
                  <span className="flex items-center">
                    <Calendar className="w-3.5 h-3.5 mr-1 text-slate-400" />
                    {job.scheduled_at ? new Date(job.scheduled_at).toLocaleDateString() : '—'}
                  </span>
                </div>
              </div>

              <div className="flex items-center justify-between sm:justify-end sm:space-x-3 text-right">
                <div>
                  <span className="text-sm font-bold text-slate-900 block">
                    ₹{job.amount}
                  </span>
                  <span className="text-[11px] text-slate-400 capitalize">
                    {job.payment_status}
                  </span>
                </div>

                {job.booking_status === 'mechanic_en_route' && onRecordArrival && (
                  <button
                    onClick={() => onRecordArrival(job)}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-2xs transition"
                  >
                    I Arrived
                  </button>
                )}

                {['mechanic_arrived', 'inspection', 'awaiting_customer_approval', 'service_in_progress', 'additional_work'].includes(
                  job.booking_status
                ) && onOpenWorkbench && (
                  <button
                    onClick={() => onOpenWorkbench(job)}
                    className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-2xs transition"
                  >
                    Workbench
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
