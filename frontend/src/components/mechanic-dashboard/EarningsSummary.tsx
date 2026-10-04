import React from 'react';
import { Link } from 'react-router-dom';
import { IndianRupee, ChevronLeft, ChevronRight, CheckCircle2, Clock, RotateCcw, AlertTriangle, ArrowUpRight, Wallet } from 'lucide-react';
import { EarningsList, EarningsItem } from '../../types/mechanic-dashboard';

interface EarningsSummaryProps {
  earnings?: EarningsList;
  isLoading: boolean;
  page: number;
  pageSize: number;
  onPageChange: (newPage: number) => void;
  statusFilter: string;
  onStatusFilterChange: (newStatus: string) => void;
}

export const EarningsSummary: React.FC<EarningsSummaryProps> = ({
  earnings,
  isLoading,
  page,
  pageSize,
  onPageChange,
  statusFilter,
  onStatusFilterChange,
}) => {
  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'paid':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            Paid
          </span>
        );
      case 'pending':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
            <Clock className="w-3 h-3 mr-1" />
            Pending
          </span>
        );
      case 'refunded':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-800">
            <RotateCcw className="w-3 h-3 mr-1" />
            Refunded
          </span>
        );
      case 'failed':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800">
            <AlertTriangle className="w-3 h-3 mr-1" />
            Failed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
            {status}
          </span>
        );
    }
  };

  const total = earnings?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h3 className="text-base font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <IndianRupee className="w-5 h-5 text-emerald-600" />
            <span>Earnings Breakdown</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Service revenues, approved additions, and net mechanic payouts
          </p>
        </div>

        {/* Action Links & Status Filter Tabs */}
        <div className="flex flex-wrap items-center gap-3">
          <Link
            to="/mechanic/payouts"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200/80 transition"
          >
            <Wallet className="w-3.5 h-3.5" />
            <span>Authoritative Payout Ledger</span>
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>

          <div className="flex items-center space-x-1.5 bg-slate-100 p-1 rounded-xl text-xs font-medium text-slate-600">
            {['all', 'paid', 'pending', 'refunded'].map((st) => (
              <button
                key={st}
                onClick={() => onStatusFilterChange(st)}
                className={`px-3 py-1 rounded-lg capitalize transition ${
                  statusFilter === st
                    ? 'bg-white text-slate-900 font-bold shadow-xs'
                    : 'hover:text-slate-900'
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="animate-pulse space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-14 bg-slate-100 rounded-xl" />
          ))}
        </div>
      ) : !earnings || earnings.items.length === 0 ? (
        <div className="py-12 text-center text-slate-400 space-y-2">
          <IndianRupee className="w-8 h-8 text-slate-300 mx-auto" />
          <p className="text-sm font-medium">No earnings recorded for this selection</p>
          <p className="text-xs text-slate-400">
            Completed service bookings and payouts will be listed here.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-100 text-slate-400 font-semibold uppercase tracking-wider text-[11px]">
                <th className="pb-3">Booking #</th>
                <th className="pb-3">Gross Base</th>
                <th className="pb-3">Add'l Work</th>
                <th className="pb-3">Net Attributable</th>
                <th className="pb-3">Status</th>
                <th className="pb-3 text-right">Settled At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {earnings.items.map((item: EarningsItem) => (
                <tr key={item.booking_id} className="hover:bg-slate-50/60 transition">
                  <td className="py-3.5 font-bold text-slate-900">
                    {item.booking_number}
                  </td>
                  <td className="py-3.5 font-medium text-slate-600">
                    ₹{item.gross_amount}
                  </td>
                  <td className="py-3.5 font-medium text-slate-600">
                    ₹{item.additional_work_amount}
                  </td>
                  <td className="py-3.5 font-bold text-emerald-600 text-sm">
                    ₹{item.net_amount}
                  </td>
                  <td className="py-3.5">
                    {getStatusBadge(item.payment_status)}
                  </td>
                  <td className="py-3.5 text-right text-slate-500 font-medium">
                    {item.paid_at
                      ? new Date(item.paid_at).toLocaleDateString()
                      : item.completed_at
                      ? new Date(item.completed_at).toLocaleDateString()
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination Bar */}
      {total > pageSize && (
        <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>
            Showing <span className="font-semibold text-slate-800">{page * pageSize + 1}</span> to{' '}
            <span className="font-semibold text-slate-800">
              {Math.min((page + 1) * pageSize, total)}
            </span>{' '}
            of <span className="font-semibold text-slate-800">{total}</span> records
          </span>
          <div className="flex items-center space-x-1.5">
            <button
              onClick={() => onPageChange(page - 1)}
              disabled={page === 0}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition"
              title="Previous Page"
            >
              <ChevronLeft className="w-4 h-4 text-slate-600" />
            </button>
            <span className="px-2 font-medium">
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages - 1}
              className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition"
              title="Next Page"
            >
              <ChevronRight className="w-4 h-4 text-slate-600" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
