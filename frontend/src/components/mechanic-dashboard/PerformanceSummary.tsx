import React from 'react';
import { Award, CheckCircle2, XCircle, TrendingUp, Calendar } from 'lucide-react';
import { MechanicPerformance } from '../../types/mechanic-dashboard';

interface PerformanceSummaryProps {
  performance?: MechanicPerformance;
  isLoading: boolean;
}

export const PerformanceSummary: React.FC<PerformanceSummaryProps> = ({
  performance,
  isLoading,
}) => {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm animate-pulse space-y-4">
        <div className="w-40 h-6 bg-slate-200 rounded" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-16 bg-slate-100 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const p = performance || {
    total_jobs: 0,
    completed_jobs: 0,
    cancelled_jobs: 0,
    active_jobs: 0,
    completion_rate: 0,
    average_rating: 0,
    review_count: 0,
    rating_distribution: { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 },
    monthly_breakdown: [],
  };

  return (
    <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <Award className="w-5 h-5 text-emerald-600" />
            <span>Operational Performance</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Completion metrics and delivery reliability
          </p>
        </div>
        <div className="text-right">
          <span className="text-xs font-semibold px-2.5 py-1 bg-emerald-50 text-emerald-700 rounded-full">
            {p.completion_rate}% Completion Rate
          </span>
        </div>
      </div>

      {/* KPI Stats Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
        <div className="p-4 rounded-xl bg-slate-50 border border-slate-100">
          <span className="text-xs font-medium text-slate-500 block">Total Jobs</span>
          <span className="text-xl sm:text-2xl font-bold text-slate-900 mt-1 block">
            {p.total_jobs}
          </span>
        </div>
        <div className="p-4 rounded-xl bg-emerald-50/60 border border-emerald-100">
          <span className="text-xs font-medium text-emerald-800 flex items-center">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
            Completed
          </span>
          <span className="text-xl sm:text-2xl font-bold text-emerald-900 mt-1 block">
            {p.completed_jobs}
          </span>
        </div>
        <div className="p-4 rounded-xl bg-rose-50/60 border border-rose-100">
          <span className="text-xs font-medium text-rose-800 flex items-center">
            <XCircle className="w-3.5 h-3.5 mr-1" />
            Cancelled
          </span>
          <span className="text-xl sm:text-2xl font-bold text-rose-900 mt-1 block">
            {p.cancelled_jobs}
          </span>
        </div>
        <div className="p-4 rounded-xl bg-amber-50/60 border border-amber-100">
          <span className="text-xs font-medium text-amber-800 flex items-center">
            <TrendingUp className="w-3.5 h-3.5 mr-1" />
            Active
          </span>
          <span className="text-xl sm:text-2xl font-bold text-amber-900 mt-1 block">
            {p.active_jobs}
          </span>
        </div>
      </div>

      {/* Monthly Breakdown */}
      {p.monthly_breakdown && p.monthly_breakdown.length > 0 && (
        <div className="pt-4 border-t border-slate-100">
          <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3 flex items-center">
            <Calendar className="w-4 h-4 mr-1.5 text-slate-400" />
            Monthly Activity
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 text-slate-400 font-semibold">
                  <th className="pb-2">Month</th>
                  <th className="pb-2 text-center">Completed</th>
                  <th className="pb-2 text-center">Cancelled</th>
                  <th className="pb-2 text-right">Earned</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {p.monthly_breakdown.map((m) => (
                  <tr key={m.month} className="hover:bg-slate-50/50">
                    <td className="py-2.5 font-semibold text-slate-700">{m.month}</td>
                    <td className="py-2.5 text-center text-emerald-600 font-medium">
                      {m.completed}
                    </td>
                    <td className="py-2.5 text-center text-rose-500 font-medium">
                      {m.cancelled}
                    </td>
                    <td className="py-2.5 text-right font-bold text-slate-900">
                      ₹{m.earnings}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
