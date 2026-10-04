import React from 'react';
import {
  Building2,
  CheckCircle2,
  Clock,
  AlertTriangle,
  ShieldAlert,
  ArrowUpRight,
  RefreshCw,
  Edit3,
  Loader2,
} from 'lucide-react';
import { PayoutAccount, PayoutAccountVerificationStatus } from '../../types/payoutAccount';

interface PayoutAccountStatusProps {
  account: PayoutAccount;
  onVerify: () => Promise<void>;
  onReplace: () => void;
  isVerifying?: boolean;
}

const STATUS_CONFIG: Record<
  PayoutAccountVerificationStatus,
  {
    label: string;
    description: string;
    bgColor: string;
    textColor: string;
    borderColor: string;
    icon: React.ReactNode;
  }
> = {
  verified: {
    label: 'Verified & Active',
    description: 'Direct payouts are active. Earnings are disbursed automatically to this account.',
    bgColor: 'bg-emerald-50',
    textColor: 'text-emerald-700',
    borderColor: 'border-emerald-200',
    icon: <CheckCircle2 className="w-4 h-4 text-emerald-600" />,
  },
  pending: {
    label: 'Pending Verification',
    description: 'Bank details submitted. Penny-drop validation is required before payouts can be issued.',
    bgColor: 'bg-amber-50',
    textColor: 'text-amber-700',
    borderColor: 'border-amber-200',
    icon: <Clock className="w-4 h-4 text-amber-600" />,
  },
  submitted: {
    label: 'Submitted to Provider',
    description: 'Account sent to RazorpayX. Awaiting automated penny-drop validation response.',
    bgColor: 'bg-blue-50',
    textColor: 'text-blue-700',
    borderColor: 'border-blue-200',
    icon: <ArrowUpRight className="w-4 h-4 text-blue-600" />,
  },
  failed: {
    label: 'Verification Failed',
    description: 'Beneficiary name mismatch or invalid IFSC. Please check your bank details or replace.',
    bgColor: 'bg-rose-50',
    textColor: 'text-rose-700',
    borderColor: 'border-rose-200',
    icon: <AlertTriangle className="w-4 h-4 text-rose-600" />,
  },
  suspended: {
    label: 'Suspended',
    description: 'This payout account has been suspended by risk operations. Contact support.',
    bgColor: 'bg-slate-100',
    textColor: 'text-slate-700',
    borderColor: 'border-slate-300',
    icon: <ShieldAlert className="w-4 h-4 text-slate-600" />,
  },
  not_configured: {
    label: 'Not Configured',
    description: 'No active bank account on file.',
    bgColor: 'bg-slate-50',
    textColor: 'text-slate-600',
    borderColor: 'border-slate-200',
    icon: <AlertTriangle className="w-4 h-4 text-slate-500" />,
  },
};

export const PayoutAccountStatus: React.FC<PayoutAccountStatusProps> = ({
  account,
  onVerify,
  onReplace,
  isVerifying = false,
}) => {
  const statusCfg = STATUS_CONFIG[account.verification_status] || STATUS_CONFIG.pending;
  const isEligibleForVerification =
    account.verification_status === 'pending' ||
    account.verification_status === 'submitted' ||
    account.verification_status === 'failed';

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
      {/* Header bar */}
      <div className="px-6 py-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-emerald-50 text-emerald-700 rounded-xl">
            <Building2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">Direct Payout Account</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Provider: <span className="font-semibold text-slate-700 uppercase">{account.provider}</span>
              {account.provider_account_id && (
                <span className="font-mono text-slate-400 ml-2">({account.provider_account_id})</span>
              )}
            </p>
          </div>
        </div>

        {/* Status Pill */}
        <div
          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-semibold ${statusCfg.bgColor} ${statusCfg.textColor} ${statusCfg.borderColor}`}
        >
          {statusCfg.icon}
          <span>{statusCfg.label}</span>
        </div>
      </div>

      {/* Account Details Body */}
      <div className="p-6 sm:p-8 space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
          {/* Account Number */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Account Number
            </span>
            <p className="text-base font-mono font-bold text-slate-800 tracking-wider">
              {account.account_number_masked}
            </p>
          </div>

          {/* Account Holder Name */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Account Holder
            </span>
            <p className="text-base font-semibold text-slate-800">
              {account.account_holder_name}
            </p>
          </div>

          {/* Bank & IFSC */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Bank & IFSC
            </span>
            <p className="text-sm font-semibold text-slate-800">
              {account.bank_name || 'Bank'} • <span className="font-mono text-slate-600">{account.ifsc_code || 'N/A'}</span>
            </p>
          </div>
        </div>

        {/* Verification Description & Details */}
        <div className={`p-4 rounded-xl border ${statusCfg.bgColor} ${statusCfg.borderColor} flex items-start gap-3`}>
          <div className="mt-0.5">{statusCfg.icon}</div>
          <div className="space-y-1 text-xs">
            <p className={`font-semibold ${statusCfg.textColor}`}>{statusCfg.description}</p>
            {account.verified_at && (
              <p className="text-slate-500">
                Verified on: {new Date(account.verified_at).toLocaleString()}
              </p>
            )}
            {account.verification_details?.registered_name && (
              <p className="text-slate-600">
                Bank Registered Name:{' '}
                <span className="font-semibold text-slate-800">
                  {account.verification_details.registered_name}
                </span>
              </p>
            )}
          </div>
        </div>

        {/* Actions Row */}
        <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-100">
          <div className="text-xs text-slate-400">
            Account ID: <span className="font-mono text-slate-500">{account.id.slice(0, 8)}...</span>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            {isEligibleForVerification && (
              <button
                type="button"
                onClick={onVerify}
                disabled={isVerifying}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-semibold hover:bg-emerald-700 transition disabled:opacity-50"
              >
                {isVerifying ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Verifying with Bank...</span>
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>Trigger Penny-Drop Verification</span>
                  </>
                )}
              </button>
            )}

            <button
              type="button"
              onClick={onReplace}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2 border border-slate-300 text-slate-700 bg-white rounded-xl text-xs font-semibold hover:bg-slate-50 transition"
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Replace Bank Account</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
