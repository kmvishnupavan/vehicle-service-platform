import React from 'react';
import { Calendar, Wrench, CheckCircle2, IndianRupee, Clock, XCircle } from 'lucide-react';
import { DashboardOverview } from '../../types/mechanic-dashboard';

interface OverviewCardsProps {
  overview?: DashboardOverview;
  isLoading: boolean;
}

export const OverviewCards: React.FC<OverviewCardsProps> = ({ overview, isLoading }) => {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6 mb-8">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm animate-pulse space-y-4"
          >
            <div className="flex justify-between items-center">
              <div className="w-10 h-10 bg-slate-200 rounded-xl" />
              <div className="w-16 h-4 bg-slate-200 rounded-full" />
            </div>
            <div className="w-24 h-8 bg-slate-200 rounded" />
            <div className="w-32 h-4 bg-slate-200 rounded" />
          </div>
        ))}
      </div>
    );
  }

  const today = overview?.today || { jobs: 0, completed: 0, cancelled: 0 };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6 mb-8">
      {/* Today's Jobs Card */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm hover:shadow-md transition">
        <div className="flex justify-between items-start">
          <div className="w-11 h-11 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center">
            <Calendar className="w-5 h-5" />
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 bg-blue-50 text-blue-700 rounded-full">
            Today
          </span>
        </div>
        <div className="mt-4">
          <h3 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
            {today.jobs}
          </h3>
          <p className="text-sm font-medium text-slate-500 mt-1">Today's Jobs</p>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span className="flex items-center text-emerald-600">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            {today.completed} completed
          </span>
          <span className="flex items-center text-rose-500">
            <XCircle className="w-3.5 h-3.5 mr-1" />
            {today.cancelled} cancelled
          </span>
        </div>
      </div>

      {/* Active Jobs Card */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm hover:shadow-md transition">
        <div className="flex justify-between items-start">
          <div className="w-11 h-11 bg-amber-50 text-amber-600 rounded-xl flex items-center justify-center">
            <Wrench className="w-5 h-5" />
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 bg-amber-50 text-amber-700 rounded-full">
            In Progress
          </span>
        </div>
        <div className="mt-4">
          <h3 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
            {overview?.active_jobs ?? 0}
          </h3>
          <p className="text-sm font-medium text-slate-500 mt-1">Active Jobs</p>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-100 flex items-center text-xs text-slate-500">
          <Clock className="w-3.5 h-3.5 mr-1.5 text-amber-500" />
          <span>Requires prompt attention</span>
        </div>
      </div>

      {/* Completed Jobs Card */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm hover:shadow-md transition">
        <div className="flex justify-between items-start">
          <div className="w-11 h-11 bg-emerald-50 text-emerald-600 rounded-xl flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 bg-emerald-50 text-emerald-700 rounded-full">
            Lifetime
          </span>
        </div>
        <div className="mt-4">
          <h3 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
            {overview?.completed_jobs ?? 0}
          </h3>
          <p className="text-sm font-medium text-slate-500 mt-1">Completed Services</p>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>Completion rate</span>
          <span className="font-semibold text-emerald-600">
            {overview?.completion_rate ?? 0}%
          </span>
        </div>
      </div>

      {/* Total Earnings Card */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm hover:shadow-md transition">
        <div className="flex justify-between items-start">
          <div className="w-11 h-11 bg-emerald-600 text-white rounded-xl flex items-center justify-center shadow-sm">
            <IndianRupee className="w-5 h-5" />
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 bg-emerald-100 text-emerald-800 rounded-full">
            Settled
          </span>
        </div>
        <div className="mt-4">
          <h3 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
            ₹{overview?.total_earnings ?? '0.00'}
          </h3>
          <p className="text-sm font-medium text-slate-500 mt-1">Total Earned</p>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>Pending settlement</span>
          <span className="font-semibold text-amber-600">
            ₹{overview?.pending_earnings ?? '0.00'}
          </span>
        </div>
      </div>
    </div>
  );
};
