import React, { useState } from 'react';
import { Sliders, ShieldCheck, AlertCircle } from 'lucide-react';
import { SettlementApprovalPolicy } from '../../types/settlement';

interface SettlementPolicyModalProps {
  policy?: SettlementApprovalPolicy | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (thresholdAmount: number, requiresChecker: boolean) => Promise<void>;
  isLoading: boolean;
}

export const SettlementPolicyModal: React.FC<SettlementPolicyModalProps> = ({
  policy,
  isOpen,
  onClose,
  onSave,
  isLoading,
}) => {
  const [threshold, setThreshold] = useState<string>(
    policy ? String(policy.threshold_amount) : '0.00'
  );
  const [requiresChecker, setRequiresChecker] = useState<boolean>(
    policy ? policy.requires_checker : true
  );
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const num = parseFloat(threshold);
    if (isNaN(num) || num < 0) {
      setError('Please enter a valid non-negative threshold amount.');
      return;
    }
    setError(null);
    try {
      await onSave(num, requiresChecker);
      onClose();
    } catch (err: any) {
      setError(err?.message || 'Failed to update approval policy.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-100 transition-all animate-in fade-in zoom-in-95">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-3 bg-indigo-100/80 text-indigo-700 rounded-xl">
            <Sliders className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Settlement Approval Policy</h3>
            <p className="text-xs text-slate-500">Configure maker-checker risk controls</p>
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
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              High-Value Approval Threshold (INR)
            </label>
            <div className="relative">
              <span className="absolute inset-y-0 left-0 pl-3 flex items-center text-xs font-bold text-slate-400">
                ₹
              </span>
              <input
                type="number"
                step="0.01"
                min="0"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                className="w-full pl-8 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent font-mono text-slate-800"
              />
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              Set to 0.00 to enforce two-person review on ALL settlement disbursements (safest).
            </p>
          </div>

          <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/60 flex items-start gap-3">
            <input
              type="checkbox"
              id="requires_checker_checkbox"
              checked={requiresChecker}
              onChange={(e) => setRequiresChecker(e.target.checked)}
              className="mt-0.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            <label htmlFor="requires_checker_checkbox" className="text-xs text-slate-700 cursor-pointer">
              <span className="font-semibold block text-slate-900">Always Require Checker</span>
              <span className="text-[11px] text-slate-500 leading-tight">
                Mandates secondary checker approval regardless of batch amount size.
              </span>
            </label>
          </div>

          <div className="p-3 bg-emerald-50/70 border border-emerald-100 rounded-xl flex items-center gap-2 text-xs text-emerald-800">
            <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>All policy updates are permanently audited in public.audit_logs.</span>
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
              className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-lg transition shadow-sm flex items-center gap-1.5"
            >
              {isLoading && (
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              <span>Save Policy</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
