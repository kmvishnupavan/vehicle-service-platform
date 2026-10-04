import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  Building2,
  ShieldCheck,
  AlertTriangle,
  RotateCcw,
  CheckCircle2,
} from 'lucide-react';
import {
  usePayoutAccount,
  useSavePayoutAccount,
  useVerifyPayoutAccount,
  useSettlementHistory,
} from '../hooks/usePayoutAccount';
import { PayoutAccountForm } from '../components/mechanic-payouts/PayoutAccountForm';
import { PayoutAccountStatus } from '../components/mechanic-payouts/PayoutAccountStatus';
import { SettlementHistoryTable } from '../components/mechanic-payouts/SettlementHistoryTable';
import { PayoutAccountCreatePayload } from '../types/payoutAccount';

export const MechanicPayoutAccountPage: React.FC = () => {
  const [isReplacing, setIsReplacing] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Queries & Mutations
  const {
    data: account,
    isLoading: isAccountLoading,
    error: accountError,
    refetch: refetchAccount,
  } = usePayoutAccount();

  const {
    data: settlements,
    isLoading: isSettlementsLoading,
    refetch: refetchSettlements,
  } = useSettlementHistory();

  const saveMutation = useSavePayoutAccount();
  const verifyMutation = useVerifyPayoutAccount();

  const handleSaveAccount = async (payload: PayoutAccountCreatePayload) => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      await saveMutation.mutateAsync(payload);
      setIsReplacing(false);
      setSuccessMessage('Bank account saved successfully! Trigger penny-drop to verify.');
    } catch (err: any) {
      setErrorMessage(err?.message || 'Failed to save bank account. Please check your inputs.');
    }
  };

  const handleVerifyAccount = async () => {
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await verifyMutation.mutateAsync();
      if (res.verification_status === 'verified') {
        setSuccessMessage('Penny-drop validation succeeded! Your bank account is verified.');
      } else {
        setSuccessMessage('Penny-drop validation initiated. Awaiting bank confirmation.');
      }
    } catch (err: any) {
      setErrorMessage(
        err?.message || 'Verification could not be completed. Please check your account details.'
      );
    }
  };

  const handleRefresh = () => {
    refetchAccount();
    refetchSettlements();
  };

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16">
      {/* Header Banner */}
      <div className="bg-white border-b border-slate-200/80 sticky top-16 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Link
                  to="/mechanic/dashboard"
                  className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-emerald-600 transition"
                >
                  <ArrowLeft className="w-3.5 h-3.5 mr-1" />
                  Dashboard
                </Link>
                <span className="text-slate-300">/</span>
                <Link
                  to="/mechanic/payouts"
                  className="inline-flex items-center text-xs font-semibold text-slate-500 hover:text-emerald-600 transition"
                >
                  Payouts
                </Link>
                <span className="text-slate-300">/</span>
                <span className="text-xs font-semibold text-emerald-600">
                  Banking & Onboarding
                </span>
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                <div className="p-2 bg-emerald-100/70 text-emerald-700 rounded-lg">
                  <Building2 className="w-6 h-6" />
                </div>
                <span>Mechanic Banking & Payout Settings</span>
              </h1>
            </div>

            <div className="flex items-center gap-2 text-xs font-medium text-slate-500 bg-slate-100/70 px-3 py-2 rounded-lg border border-slate-200/60">
              <ShieldCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>RazorpayX Provider Integration • RBI & NPCI Compliant</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {/* Success Alert */}
        {successMessage && (
          <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <p className="text-xs font-semibold text-emerald-800">{successMessage}</p>
            </div>
            <button
              onClick={() => setSuccessMessage(null)}
              className="text-xs font-semibold text-emerald-700 hover:text-emerald-900"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Error Alert */}
        {errorMessage && (
          <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
              <div>
                <h4 className="text-xs font-bold text-rose-900">Action Failed</h4>
                <p className="text-xs text-rose-700">{errorMessage}</p>
              </div>
            </div>
            <button
              onClick={() => setErrorMessage(null)}
              className="text-xs font-semibold text-rose-700 hover:text-rose-900"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Account Query Error */}
        {accountError && (
          <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0" />
              <div>
                <h4 className="text-xs font-bold text-rose-900">Could not retrieve bank account</h4>
                <p className="text-xs text-rose-700">
                  {accountError instanceof Error ? accountError.message : 'Please try again.'}
                </p>
              </div>
            </div>
            <button
              onClick={handleRefresh}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-medium hover:bg-rose-700 transition"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Retry
            </button>
          </div>
        )}

        {/* 1. Account Section: Either Form or Status Card */}
        <section aria-label="Bank Account Onboarding">
          {isAccountLoading ? (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center text-slate-500">
              <div className="w-8 h-8 border-3 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              Loading banking profile...
            </div>
          ) : !account || isReplacing ? (
            <PayoutAccountForm
              initialValues={
                account
                  ? {
                      account_holder_name: account.account_holder_name,
                      bank_name: account.bank_name || undefined,
                      ifsc_code: account.ifsc_code || undefined,
                    }
                  : undefined
              }
              onSubmit={handleSaveAccount}
              onCancel={account ? () => setIsReplacing(false) : undefined}
              isSubmitting={saveMutation.isPending}
              isReplacing={isReplacing}
            />
          ) : (
            <PayoutAccountStatus
              account={account}
              onVerify={handleVerifyAccount}
              onReplace={() => setIsReplacing(true)}
              isVerifying={verifyMutation.isPending}
            />
          )}
        </section>

        {/* 2. Settlement Disbursements History */}
        <section aria-label="Settlement History">
          <SettlementHistoryTable
            items={settlements || []}
            isLoading={isSettlementsLoading}
          />
        </section>
      </div>
    </div>
  );
};
