import React, { useState } from 'react';
import {
  CreditCard,
  CheckCircle,
  AlertCircle,
  Lock,
  X,
  Receipt,
  ShieldCheck,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useBookingInvoice, useCreatePaymentOrder, useVerifyPayment } from '../../hooks/usePayment';

interface PaymentModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookingId: string;
  bookingNumber: string;
  totalAmount: string | number;
  onSuccess?: () => void;
}

export const PaymentModal: React.FC<PaymentModalProps> = ({
  isOpen,
  onClose,
  bookingId,
  bookingNumber,
  totalAmount,
  onSuccess,
}) => {
  const { user } = useAuth();
  const createOrderMutation = useCreatePaymentOrder();
  const verifyMutation = useVerifyPayment();
  const { data: invoice } = useBookingInvoice(bookingId);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  if (!isOpen) return null;

  const loadRazorpayScript = (): Promise<boolean> => {
    return new Promise((resolve) => {
      if ((window as any).Razorpay) {
        resolve(true);
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://checkout.razorpay.com/v1/checkout.js';
      script.onload = () => resolve(true);
      script.onerror = () => resolve(false);
      document.body.appendChild(script);
    });
  };

  const handlePayNow = async () => {
    setError(null);
    setIsProcessing(true);

    try {
      // 1. Create authoritative order on FastAPI backend
      const order = await createOrderMutation.mutateAsync(bookingId);

      // 2. Load Razorpay Checkout SDK
      const isLoaded = await loadRazorpayScript();
      if (!isLoaded || !(window as any).Razorpay) {
        throw new Error('Razorpay Checkout failed to initialize. Please check internet connection.');
      }

      // 3. Open Razorpay Checkout modal
      const options = {
        key: order.key_id,
        amount: order.amount,
        currency: order.currency || 'INR',
        name: 'VehicleCare Service Platform',
        description: `Settlement for #${bookingNumber}`,
        order_id: order.order_id,
        handler: async (response: {
          razorpay_payment_id: string;
          razorpay_order_id: string;
          razorpay_signature: string;
        }) => {
          try {
            await verifyMutation.mutateAsync({
              booking_id: bookingId,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            setSuccess(true);
            setTimeout(() => {
              onSuccess?.();
              onClose();
            }, 1500);
          } catch (err: any) {
            setError(err?.message || 'Payment settlement verification failed.');
          } finally {
            setIsProcessing(false);
          }
        },
        prefill: {
          name: user?.user_metadata?.full_name || 'Valued Customer',
          email: user?.email || '',
        },
        theme: {
          color: '#059669',
        },
        modal: {
          ondismiss: () => {
            setIsProcessing(false);
          },
        },
      };

      const razorpayInstance = new (window as any).Razorpay(options);
      razorpayInstance.on('payment.failed', (resp: any) => {
        setError(resp.error?.description || 'Payment was declined or cancelled.');
        setIsProcessing(false);
      });
      razorpayInstance.open();
    } catch (err: any) {
      setError(err?.message || 'Failed to initiate checkout order.');
      setIsProcessing(false);
    }
  };

  const formattedAmount = parseFloat(String(totalAmount || 0)).toFixed(2);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden">
        {/* Modal Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center space-x-2.5">
            <div className="p-2 bg-emerald-100 text-emerald-700 rounded-xl">
              <CreditCard className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base">Service Settlement</h3>
              <p className="text-[11px] text-slate-500 font-medium">#{bookingNumber}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isProcessing}
            className="p-1 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-5">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-3.5 rounded-xl flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {success ? (
            <div className="py-6 text-center space-y-3">
              <CheckCircle className="w-12 h-12 text-emerald-600 mx-auto animate-bounce" />
              <h4 className="text-base font-bold text-slate-900">Payment Succeeded!</h4>
              <p className="text-xs text-slate-600">
                Your payment has been cryptographically verified and settled. Updating invoice...
              </p>
            </div>
          ) : (
            <>
              {/* Invoice Summary Box */}
              <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-4 space-y-2.5 text-xs text-slate-600">
                <div className="flex items-center justify-between text-slate-900 font-semibold border-b border-slate-200/60 pb-2">
                  <span className="flex items-center space-x-1.5">
                    <Receipt className="w-4 h-4 text-emerald-600" />
                    <span>Official Tax Invoice</span>
                  </span>
                  <span className="text-[11px] text-slate-500 font-mono">
                    {invoice?.invoice_number || 'INV-PENDING'}
                  </span>
                </div>

                <div className="flex justify-between">
                  <span>Service Subtotal</span>
                  <span>₹{parseFloat(String(invoice?.subtotal || formattedAmount)).toFixed(2)}</span>
                </div>

                {invoice?.tax ? (
                  <div className="flex justify-between">
                    <span>GST (18%)</span>
                    <span>₹{parseFloat(String(invoice.tax)).toFixed(2)}</span>
                  </div>
                ) : null}

                <div className="flex justify-between items-center text-sm font-bold text-slate-900 pt-2 border-t border-slate-200/60">
                  <span>Grand Total</span>
                  <span className="text-lg text-emerald-700 font-black">₹{formattedAmount}</span>
                </div>
              </div>

              {/* Security Pill */}
              <div className="flex items-center justify-between px-3 py-2 bg-emerald-50/70 border border-emerald-100 rounded-xl text-[11px] text-emerald-800 font-medium">
                <span className="flex items-center space-x-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  <span>Razorpay Test Sandbox Enabled</span>
                </span>
                <span className="flex items-center space-x-1 font-semibold text-slate-600">
                  <Lock className="w-3 h-3 text-slate-400" />
                  <span>256-bit SSL</span>
                </span>
              </div>

              {/* Pay Now Button */}
              <button
                onClick={handlePayNow}
                disabled={isProcessing}
                className="w-full py-3 px-4 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 text-white rounded-xl text-sm font-bold shadow-md hover:shadow-lg transition flex items-center justify-center space-x-2"
              >
                {isProcessing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Opening Razorpay Sandbox...</span>
                  </>
                ) : (
                  <>
                    <CreditCard className="w-4 h-4" />
                    <span>Pay ₹{formattedAmount} Now</span>
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
