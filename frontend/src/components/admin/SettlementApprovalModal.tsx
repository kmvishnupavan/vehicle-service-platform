import React, { useState } from 'react';
import { CheckCircle2, XCircle, AlertCircle, ShieldAlert } from 'lucide-react';
import { SettlementBatchItem } from '../../types/settlement';

interface SettlementApprovalModalProps {
  batch: SettlementBatchItem;
  action: 'approve' | 'reject';
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (reason?: string) => Promise<void>;
  isLoading: boolean;
}

export const SettlementApprovalModal: React.FC<SettlementApprovalModalProps> = ({
  batch,
  action,
  isOpen,
  onClose,
  onConfirm,
  isLoading,
}) => {
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const isApprove = action === 'approve';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isApprove && !reason.trim()) {
      setError('A rejection reason is required for audit records.');
      return;
    }
    setError(null);
    try {
      await onConfirm(reason.trim() || undefined);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Action failed. Please try again.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-100 transition-all animate-in fade-in zoom-in-95">
        <div className="flex items-center gap-3 mb-4">
          <div
            className={`p-3 rounded-xl ${
              isApprove ? 'bg-emerald-100/80 text-emerald-700' : 'bg-rose-100/80 text-rose-700'
            }`}
          >
            {isApprove ? <CheckCircle2 className="w-6 h-6" /> : <XCircle className="w-6 h-6" />}
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              {isApprove ? 'Approve Settlement Batch' : 'Reject Settlement Batch'}
            </h3>
            <p className="text-xs text-slate-500 font-mono mt-0.5">{batch.batch_number}</p>
          </div>
        </div>

        {/* Informational Card */}
        <div className="bg-slate-50 rounded-xl p-4 mb-4 border border-slate-200/60 text-xs text-slate-600 space-y-2">
          <div className="flex justify-between">
            <span className="text-slate-500">Total Net Disbursable:</span>
            <span className="font-bold text-slate-900">
              INR {Number(batch.total_amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Payout Records:</span>
            <span className="font-semibold text-slate-800">{batch.item_count} items</span>
          </div>
          <div className="pt-2 border-t border-slate-200/60 flex items-start gap-2 text-slate-600">
            <ShieldAlert className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <p className="text-[11px] leading-relaxed">
              {isApprove
                ? 'Approval transitions this batch into an immutable financial state. Records cannot be edited after approval.'
                : 'Rejecting this batch unlinks the associated ledger items back into the pool for future batches.'}
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center gap-2 text-xs text-rose-700">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1.5">
              {isApprove ? 'Approval Notes (Optional)' : 'Rejection Reason (Required)'}
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                isApprove
                  ? 'e.g., Verified ledger bank details and commission breakdown.'
                  : 'e.g., Mismatch in booking amounts, requires recalculation.'
              }
              rows={3}
              className="w-full text-xs rounded-xl border border-slate-200 p-3 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent text-slate-800"
            />
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className={`px-4 py-2 text-xs font-semibold text-white rounded-lg transition shadow-sm flex items-center gap-1.5 ${
                isApprove
                  ? 'bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400'
                  : 'bg-rose-600 hover:bg-rose-700 disabled:bg-rose-400'
              }`}
            >
              {isLoading && (
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              <span>{isApprove ? 'Confirm Approval' : 'Confirm Rejection'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
