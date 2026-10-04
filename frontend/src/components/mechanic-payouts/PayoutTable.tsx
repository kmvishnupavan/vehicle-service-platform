import React, { useState } from 'react';
import {
  FileText,
  ChevronRight,
  ChevronDown,
  Info,
  Calendar,
  Layers,
  ChevronLeft,
} from 'lucide-react';
import { PayoutItem } from '../../types/payout';
import { PayoutStatusBadge } from './PayoutStatusBadge';

interface PayoutTableProps {
  items: PayoutItem[];
  total: number;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
  isLoading?: boolean;
}

export const PayoutTable: React.FC<PayoutTableProps> = ({
  items,
  total,
  limit,
  offset,
  onPageChange,
  isLoading = false,
}) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const formatCurrency = (val?: string) => {
    const num = parseFloat(val || '0.00');
    return `₹${num.toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return isoString;
    }
  };

  const formatDateTime = (isoString?: string | null) => {
    if (!isoString) return '—';
    try {
      const d = new Date(isoString);
      return d.toLocaleString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoString;
    }
  };

  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-sm p-8 text-center">
        <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-500 font-medium">Loading authoritative payout ledger...</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-sm p-12 text-center">
        <div className="w-12 h-12 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-4 text-slate-400">
          <Layers className="w-6 h-6" />
        </div>
        <h3 className="text-base font-bold text-slate-800 mb-1">No Payout Records Found</h3>
        <p className="text-sm text-slate-500 max-w-sm mx-auto">
          No settlements or payout ledger entries match the selected filters. Completed booking payments will appear here automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200/80 shadow-sm overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50/80 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200/80">
            <tr>
              <th scope="col" className="px-5 py-3.5">
                Booking
              </th>
              <th scope="col" className="px-5 py-3.5">
                Gross Service
              </th>
              <th scope="col" className="px-5 py-3.5">
                Platform Comm.
              </th>
              <th scope="col" className="px-5 py-3.5">
                Deductions
              </th>
              <th scope="col" className="px-5 py-3.5">
                Net Payout
              </th>
              <th scope="col" className="px-5 py-3.5">
                Status
              </th>
              <th scope="col" className="px-5 py-3.5">
                Settled Date
              </th>
              <th scope="col" className="px-5 py-3.5 text-right">
                Details
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((payout) => {
              const isExpanded = expandedId === payout.id;
              const commPercent = Math.round(parseFloat(payout.commission_rate || '0') * 100);

              return (
                <React.Fragment key={payout.id}>
                  <tr
                    onClick={() => toggleExpand(payout.id)}
                    className="hover:bg-slate-50/70 transition-colors cursor-pointer"
                  >
                    {/* Booking Number */}
                    <td className="px-5 py-4">
                      <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                        <FileText className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                        <span>{payout.booking_number || 'BK-SERVICE'}</span>
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {formatDate(payout.created_at)}
                      </div>
                    </td>

                    {/* Gross */}
                    <td className="px-5 py-4 font-medium text-slate-800">
                      {formatCurrency(payout.gross_amount)}
                    </td>

                    {/* Commission */}
                    <td className="px-5 py-4 text-slate-600">
                      <div className="text-rose-600 font-medium">
                        -{formatCurrency(payout.commission_amount)}
                      </div>
                      <div className="text-xs text-slate-400">
                        {commPercent}% rate
                      </div>
                    </td>

                    {/* Deductions */}
                    <td className="px-5 py-4 text-slate-600">
                      {parseFloat(payout.deduction_amount) > 0 ? (
                        <span className="text-rose-600 font-medium">
                          -{formatCurrency(payout.deduction_amount)}
                        </span>
                      ) : (
                        <span className="text-slate-400">₹0.00</span>
                      )}
                    </td>

                    {/* Net Payout */}
                    <td className="px-5 py-4">
                      <span className="font-bold text-emerald-700 text-base">
                        {formatCurrency(payout.net_amount)}
                      </span>
                    </td>

                    {/* Status Badge */}
                    <td className="px-5 py-4">
                      <PayoutStatusBadge status={payout.status} />
                    </td>

                    {/* Settlement Date */}
                    <td className="px-5 py-4 text-xs text-slate-600">
                      {payout.settled_at ? (
                        <div>
                          <div className="font-medium text-slate-800">
                            {formatDate(payout.settled_at)}
                          </div>
                          <div className="text-[11px] text-slate-400">Bank Settled</div>
                        </div>
                      ) : payout.eligible_at ? (
                        <div>
                          <div className="font-medium text-blue-700">
                            {formatDate(payout.eligible_at)}
                          </div>
                          <div className="text-[11px] text-slate-400">Cleared Eligible</div>
                        </div>
                      ) : (
                        <span className="text-slate-400">Pending Hold</span>
                      )}
                    </td>

                    {/* Expand Toggle */}
                    <td className="px-5 py-4 text-right">
                      <button
                        type="button"
                        className="text-slate-400 hover:text-slate-600 p-1 rounded-md"
                        aria-label={isExpanded ? 'Collapse breakdown' : 'Expand breakdown'}
                      >
                        {isExpanded ? (
                          <ChevronDown className="w-5 h-5 text-slate-600" />
                        ) : (
                          <ChevronRight className="w-5 h-5" />
                        )}
                      </button>
                    </td>
                  </tr>

                  {/* Expanded Itemized Financial Breakdown (Sections 18 & 19) */}
                  {isExpanded && (
                    <tr className="bg-slate-50/60 border-t border-b border-slate-200/60">
                      <td colSpan={8} className="px-6 py-4">
                        <div className="max-w-2xl bg-white rounded-lg p-4 border border-slate-200/80 shadow-sm space-y-3">
                          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                            <span className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                              <Info className="w-4 h-4 text-emerald-600" />
                              Itemized Payout Settlement Breakdown
                            </span>
                            <span className="text-xs text-slate-400 font-mono">
                              Ref: {payout.id.slice(0, 8)}...
                            </span>
                          </div>

                          {/* Financial Formula Lines */}
                          <div className="space-y-1.5 text-xs">
                            <div className="flex justify-between items-center text-slate-700">
                              <span>Customer-Paid Service Gross Amount:</span>
                              <span className="font-semibold text-slate-900 font-mono">
                                {formatCurrency(payout.gross_amount)}
                              </span>
                            </div>

                            <div className="flex justify-between items-center text-rose-600">
                              <span>
                                Platform Commission ({commPercent}% applied rate):
                              </span>
                              <span className="font-semibold font-mono">
                                -{formatCurrency(payout.commission_amount)}
                              </span>
                            </div>

                            <div className="flex justify-between items-center text-slate-600">
                              <span>Other Service Deductions:</span>
                              <span className="font-semibold font-mono">
                                -{formatCurrency(payout.deduction_amount)}
                              </span>
                            </div>

                            <div className="pt-2 border-t border-slate-200 flex justify-between items-center text-sm font-bold text-emerald-700">
                              <span>Net Mechanic Payout:</span>
                              <span className="font-mono text-base">
                                {formatCurrency(payout.net_amount)}
                              </span>
                            </div>
                          </div>

                          {/* Metadata & Audit Traceability */}
                          <div className="pt-2 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px] text-slate-500">
                            <div>
                              <span className="block font-medium text-slate-700">Created:</span>
                              <span>{formatDateTime(payout.created_at)}</span>
                            </div>
                            <div>
                              <span className="block font-medium text-slate-700">Eligible:</span>
                              <span>{formatDateTime(payout.eligible_at)}</span>
                            </div>
                            <div>
                              <span className="block font-medium text-slate-700">Settled:</span>
                              <span>{formatDateTime(payout.settled_at)}</span>
                            </div>
                          </div>

                          {payout.reversed_at && (
                            <div className="p-2.5 bg-purple-50 rounded border border-purple-200 text-xs text-purple-800 flex items-center gap-2">
                              <Calendar className="w-4 h-4 text-purple-600 flex-shrink-0" />
                              <span>
                                Reversal / Refund processed on{' '}
                                {formatDateTime(payout.reversed_at)}.
                              </span>
                            </div>
                          )}

                          {payout.failure_reason && (
                            <div className="p-2.5 bg-rose-50 rounded border border-rose-200 text-xs text-rose-800">
                              <span className="font-semibold">Disbursement Failure: </span>
                              {payout.failure_reason}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="px-5 py-3.5 bg-slate-50/80 border-t border-slate-200/80 flex items-center justify-between text-xs text-slate-600">
        <div>
          Showing <span className="font-semibold">{Math.min(offset + 1, total)}</span> to{' '}
          <span className="font-semibold">{Math.min(offset + limit, total)}</span> of{' '}
          <span className="font-semibold">{total}</span> payouts
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            Previous
          </button>
          <span className="px-2">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={offset + limit >= total}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};
