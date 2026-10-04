import React, { useState } from 'react';
import { X, ShieldAlert } from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  bookingNumber: string;
  onSubmitDispute: (reason: string) => Promise<void>;
}

export const DisputeModal: React.FC<Props> = ({
  isOpen,
  onClose,
  bookingNumber,
  onSubmitDispute,
}) => {
  const [reason, setReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim() || reason.trim().length < 5) {
      setError('Please provide a detailed description of the dispute (at least 5 characters).');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      await onSubmitDispute(reason.trim());
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to submit dispute. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-md w-full shadow-2xl border border-slate-200 overflow-hidden transform transition-all">
        {/* Header */}
        <div className="p-5 bg-gradient-to-r from-amber-600 to-red-600 text-white flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-white/10 backdrop-blur-xs flex items-center justify-center">
              <ShieldAlert className="w-6 h-6 text-white" />
            </div>
            <div>
              <h3 className="font-bold text-base">Raise Service Dispute</h3>
              <p className="text-xs text-amber-100 font-mono">{bookingNumber}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-white/80 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs">
              {error}
            </div>
          )}

          <p className="text-xs text-slate-600 leading-relaxed">
            If you experienced an unresolved quality, parts, or billing discrepancy, our customer protection team will review your case with priority mediation.
          </p>

          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1.5">
              Explain the issue in detail:
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe what occurred, any diagnostic discrepancies, or unexpected charges..."
              rows={4}
              required
              className="w-full text-xs p-3 rounded-xl border border-slate-300 focus:outline-hidden focus:ring-2 focus:ring-amber-500 text-slate-900 placeholder:text-slate-400"
            />
          </div>

          <div className="pt-2 flex justify-end space-x-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 hover:bg-slate-100 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold transition disabled:opacity-50"
            >
              {isSubmitting ? 'Submitting...' : 'Submit Dispute'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
