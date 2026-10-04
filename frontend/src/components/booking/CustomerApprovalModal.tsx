import React, { useState } from 'react';
import {
  ShieldCheck,
  AlertCircle,
  X,
  CheckCircle2,
  Clock,
  HelpCircle,
} from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  bookingNumber: string;
  subtotal: number;
  additionalCharges: number;
  discountAmount: number;
  additionalWorkItems?: Array<{
    id: string;
    title: string;
    description: string;
    price: number;
  }>;
  onApprove: () => Promise<void>;
  onReject?: (reason: string) => Promise<void>;
}

export const CustomerApprovalModal: React.FC<Props> = ({
  isOpen,
  onClose,
  bookingNumber,
  subtotal,
  additionalCharges,
  discountAmount,
  additionalWorkItems = [],
  onApprove,
  onReject,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  // Pure financial calculations (18% GST)
  const taxableBase = Math.max(0, subtotal + additionalCharges - discountAmount);
  const taxAmount = Number((taxableBase * 0.18).toFixed(2));
  const totalAmount = Number((taxableBase + taxAmount).toFixed(2));

  const handleApprove = async () => {
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await onApprove();
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to approve estimate. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!onReject) return;
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      await onReject(rejectReason || 'Customer opted out of additional recommendations');
      onClose();
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to decline proposal.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-lg w-full shadow-2xl border border-slate-200 overflow-hidden transform transition-all animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="p-5 bg-gradient-to-r from-blue-600 to-indigo-700 text-white flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-white/10 backdrop-blur-xs flex items-center justify-center">
              <ShieldCheck className="w-6 h-6 text-white" />
            </div>
            <div>
              <h3 className="font-bold text-base">Service Authorization & Cost Estimate</h3>
              <p className="text-xs text-blue-100 font-mono">{bookingNumber}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
          {errorMessage && (
            <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Explanation Callouts */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
            <div className="flex items-start space-x-2.5">
              <HelpCircle className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
              <div>
                <h5 className="text-xs font-semibold text-slate-800">Why is this estimate presented?</h5>
                <p className="text-xs text-slate-600 mt-0.5">
                  Our certified technician inspected your vehicle and detailed all required safety services. No work begins without your explicit sign-off.
                </p>
              </div>
            </div>

            <div className="flex items-start space-x-2.5">
              <Clock className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <div>
                <h5 className="text-xs font-semibold text-slate-800">Estimated Duration</h5>
                <p className="text-xs text-slate-600 mt-0.5">
                  Approx. 45–60 minutes upon approval. You will receive live progress updates.
                </p>
              </div>
            </div>
          </div>

          {/* Additional Work Proposals List */}
          {additionalWorkItems.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2.5">
                Proposed Additional Work Items
              </h4>
              <div className="space-y-2.5">
                {additionalWorkItems.map((item) => (
                  <div key={item.id} className="p-3.5 rounded-xl border border-blue-100 bg-blue-50/40">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-slate-900">{item.title}</span>
                      <span className="text-sm font-bold text-blue-700">₹{Number(item.price).toFixed(2)}</span>
                    </div>
                    {item.description && (
                      <p className="text-xs text-slate-600 mt-1 leading-relaxed">{item.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Transparent Itemized Price Breakdown */}
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2.5">
              Itemized Cost Breakdown
            </h4>
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-2.5 text-sm">
              <div className="flex justify-between text-slate-700">
                <span>Base Scheduled Services</span>
                <span className="font-semibold text-slate-900">₹{subtotal.toFixed(2)}</span>
              </div>

              {additionalCharges > 0 && (
                <div className="flex justify-between text-blue-700">
                  <span>Additional Discovered Work</span>
                  <span className="font-semibold">₹{additionalCharges.toFixed(2)}</span>
                </div>
              )}

              {discountAmount > 0 && (
                <div className="flex justify-between text-emerald-700">
                  <span>Applied Discounts / Coupons</span>
                  <span className="font-semibold">-₹{discountAmount.toFixed(2)}</span>
                </div>
              )}

              <div className="flex justify-between text-slate-600 text-xs pt-1 border-t border-slate-200/80">
                <span>Applicable GST (18%)</span>
                <span>₹{taxAmount.toFixed(2)}</span>
              </div>

              <div className="flex justify-between text-base font-bold text-slate-900 pt-2 border-t border-slate-300">
                <span>Total Authorized Amount</span>
                <span className="text-blue-700">₹{totalAmount.toFixed(2)}</span>
              </div>
            </div>
            <p className="text-2xs text-slate-500 mt-1.5 text-center">
              * Payment is collected upon service completion after your final verification.
            </p>
          </div>

          {/* Decline Reason Field */}
          {isRejecting && (
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Reason for declining (optional):
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Let us know why you prefer not to proceed with additional work..."
                rows={2}
                className="w-full text-xs p-2.5 rounded-lg border border-slate-300 focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              />
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-end gap-2.5">
          {!isRejecting ? (
            <>
              {onReject && (
                <button
                  type="button"
                  onClick={() => setIsRejecting(true)}
                  disabled={isSubmitting}
                  className="w-full sm:w-auto px-4 py-2.5 rounded-xl border border-slate-300 text-slate-700 text-xs font-semibold hover:bg-slate-100 transition"
                >
                  Decline Additional Work
                </button>
              )}
              <button
                type="button"
                onClick={handleApprove}
                disabled={isSubmitting}
                className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700 transition flex items-center justify-center space-x-1.5 shadow-sm disabled:opacity-50"
              >
                {isSubmitting ? (
                  <span>Processing Authorization...</span>
                ) : (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    <span>Approve & Authorize Service</span>
                  </>
                )}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setIsRejecting(false)}
                disabled={isSubmitting}
                className="w-full sm:w-auto px-4 py-2 rounded-xl text-slate-600 text-xs font-semibold hover:bg-slate-200 transition"
              >
                Back to Review
              </button>
              <button
                type="button"
                onClick={handleReject}
                disabled={isSubmitting}
                className="w-full sm:w-auto px-5 py-2 rounded-xl bg-red-600 text-white text-xs font-bold hover:bg-red-700 transition disabled:opacity-50"
              >
                Confirm Decline
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
