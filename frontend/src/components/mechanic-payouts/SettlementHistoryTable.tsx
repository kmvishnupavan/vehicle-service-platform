import React from 'react';
import {
  Banknote,
  CheckCircle2,
  Clock,
  AlertTriangle,
  RotateCcw,
  Layers,
  FileDown,
} from 'lucide-react';
import { supabase } from '../../lib/supabase';
import { SettlementHistoryItem } from '../../types/payoutAccount';

interface SettlementHistoryTableProps {
  items: SettlementHistoryItem[];
  isLoading?: boolean;
}

const SETTLEMENT_STATUS_MAP: Record<
  string,
  { label: string; bg: string; text: string; border: string; icon: React.ReactNode }
> = {
  paid: {
    label: 'Settled',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
  },
  processing: {
    label: 'Processing Bank Transfer',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    icon: <Clock className="w-3.5 h-3.5 text-blue-600" />,
  },
  eligible: {
    label: 'Queued for Batch',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    icon: <Layers className="w-3.5 h-3.5 text-amber-600" />,
  },
  failed: {
    label: 'Disbursement Failed',
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    border: 'border-rose-200',
    icon: <AlertTriangle className="w-3.5 h-3.5 text-rose-600" />,
  },
  reversed: {
    label: 'Reversed',
    bg: 'bg-slate-100',
    text: 'text-slate-700',
    border: 'border-slate-200',
    icon: <RotateCcw className="w-3.5 h-3.5 text-slate-600" />,
  },
};

export const SettlementHistoryTable: React.FC<SettlementHistoryTableProps> = ({
  items,
  isLoading = false,
}) => {
  const formatCurrency = (val: string | number, curr: string = 'INR') => {
    const num = Number(val) || 0;
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: curr,
      maximumFractionDigits: 2,
    }).format(num);
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return '—';
    return new Date(dateStr).toLocaleDateString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleDownloadStatement = async (batchId: string) => {
    try {
      const session = (await supabase.auth.getSession()).data.session;
      const response = await fetch(`/api/v1/payout-accounts/settlements/${batchId}/statement`, {
        headers: {
          Authorization: `Bearer ${session?.access_token || ''}`,
        },
      });
      if (!response.ok) throw new Error('Failed to generate statement PDF');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `statement_${batchId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(e?.message || 'Failed to download statement.');
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-emerald-50 text-emerald-700 rounded-xl">
            <Banknote className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Settlement Disbursements</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Authoritative record of provider payout batches and direct bank transfers.
            </p>
          </div>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 bg-slate-100 text-slate-600 rounded-full">
          {items.length} {items.length === 1 ? 'record' : 'records'}
        </span>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="p-12 text-center text-slate-500 text-sm">
          <div className="w-8 h-8 border-3 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          Loading settlement history...
        </div>
      ) : items.length === 0 ? (
        <div className="p-12 text-center text-slate-500">
          <div className="w-12 h-12 bg-slate-100 text-slate-400 rounded-2xl flex items-center justify-center mx-auto mb-3">
            <Layers className="w-6 h-6" />
          </div>
          <h4 className="text-sm font-bold text-slate-800">No Settlement Records Yet</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
            Once customer payments are settled and payout batches run, your direct disbursement
            history will appear here.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                <th className="py-3 px-6">Payout / Batch Ref</th>
                <th className="py-3 px-6">Booking</th>
                <th className="py-3 px-6 text-right">Net Disbursed</th>
                <th className="py-3 px-6">Status</th>
                <th className="py-3 px-6">Settled Date</th>
                <th className="py-3 px-6">Notes</th>
                <th className="py-3 px-6 text-right">Statement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {items.map((item) => {
                const statusMeta =
                  SETTLEMENT_STATUS_MAP[item.status] || SETTLEMENT_STATUS_MAP.processing;

                return (
                  <tr key={item.id} className="hover:bg-slate-50/50 transition">
                    {/* Batch / Payout Reference */}
                    <td className="py-4 px-6">
                      <div className="font-mono text-xs font-semibold text-slate-900">
                        {item.batch_number ? (
                          <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
                            {item.batch_number}
                          </span>
                        ) : item.provider_payout_id ? (
                          <span>{item.provider_payout_id}</span>
                        ) : (
                          <span className="text-slate-400">#{item.id.slice(0, 8)}</span>
                        )}
                      </div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Created: {formatDate(item.created_at)}
                      </div>
                    </td>

                    {/* Booking Number */}
                    <td className="py-4 px-6">
                      <span className="font-medium text-slate-800">
                        {item.booking_number || 'Booking'}
                      </span>
                    </td>

                    {/* Net Amount */}
                    <td className="py-4 px-6 text-right">
                      <span className="font-bold text-slate-900">
                        {formatCurrency(item.net_amount, item.currency)}
                      </span>
                    </td>

                    {/* Status */}
                    <td className="py-4 px-6">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${statusMeta.bg} ${statusMeta.text} ${statusMeta.border}`}
                      >
                        {statusMeta.icon}
                        <span>{statusMeta.label}</span>
                      </span>
                    </td>

                    {/* Settled Date */}
                    <td className="py-4 px-6 text-xs text-slate-600">
                      {formatDate(item.settled_at)}
                    </td>

                    {/* Sanitized failure explanation */}
                    <td className="py-4 px-6 text-xs text-slate-500 max-w-xs">
                      {item.failure_reason ? (
                        <span className="text-rose-600 bg-rose-50 px-2 py-1 rounded border border-rose-200">
                          {item.failure_reason}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>

                    {/* Statement PDF Download */}
                    <td className="py-4 px-6 text-right">
                      {item.settlement_batch_id ? (
                        <button
                          type="button"
                          onClick={() => handleDownloadStatement(item.settlement_batch_id!)}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg border border-emerald-200 transition"
                          title="Download PDF disbursement statement"
                        >
                          <FileDown className="w-3.5 h-3.5" />
                          <span>PDF</span>
                        </button>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
