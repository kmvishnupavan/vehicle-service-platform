import React, { useState } from 'react';
import {
  Building2,
  Lock,
  AlertCircle,
  Loader2,
  ShieldCheck,
  CreditCard,
  User,
} from 'lucide-react';
import { PayoutAccountCreatePayload } from '../../types/payoutAccount';

interface PayoutAccountFormProps {
  initialValues?: {
    account_holder_name?: string;
    bank_name?: string;
    ifsc_code?: string;
  };
  onSubmit: (payload: PayoutAccountCreatePayload) => Promise<void>;
  onCancel?: () => void;
  isSubmitting?: boolean;
  isReplacing?: boolean;
}

const COMMON_BANKS = [
  'State Bank of India',
  'HDFC Bank',
  'ICICI Bank',
  'Axis Bank',
  'Punjab National Bank',
  'Bank of Baroda',
  'Kotak Mahindra Bank',
  'Canara Bank',
  'Union Bank of India',
  'IndusInd Bank',
];

export const PayoutAccountForm: React.FC<PayoutAccountFormProps> = ({
  initialValues,
  onSubmit,
  onCancel,
  isSubmitting = false,
  isReplacing = false,
}) => {
  const [holderName, setHolderName] = useState(initialValues?.account_holder_name || '');
  const [bankName, setBankName] = useState(initialValues?.bank_name || '');
  const [customBank, setCustomBank] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [confirmAccountNumber, setConfirmAccountNumber] = useState('');
  const [ifscCode, setIfscCode] = useState(initialValues?.ifsc_code || '');
  const [consentGiven, setConsentGiven] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!holderName.trim()) {
      newErrors.holderName = 'Account holder name is required.';
    } else if (holderName.trim().length < 3) {
      newErrors.holderName = 'Name must be at least 3 characters.';
    }

    const effectiveBank = bankName === 'Other' ? customBank.trim() : bankName.trim();
    if (!effectiveBank) {
      newErrors.bankName = 'Bank name is required.';
    }

    const cleanAcc = accountNumber.replace(/\s+/g, '');
    if (!cleanAcc) {
      newErrors.accountNumber = 'Account number is required.';
    } else if (!/^\d{9,18}$/.test(cleanAcc)) {
      newErrors.accountNumber = 'Account number must be between 9 and 18 digits.';
    }

    if (cleanAcc !== confirmAccountNumber.replace(/\s+/g, '')) {
      newErrors.confirmAccountNumber = 'Account numbers do not match.';
    }

    const cleanIfsc = ifscCode.trim().toUpperCase();
    if (!cleanIfsc) {
      newErrors.ifscCode = 'IFSC code is required.';
    } else if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(cleanIfsc)) {
      newErrors.ifscCode = 'Invalid IFSC format (e.g. HDFC0001234, SBIN0001234).';
    }

    if (!consentGiven) {
      newErrors.consent = 'You must affirm account ownership to continue.';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate() || isSubmitting) return;

    const effectiveBank = bankName === 'Other' ? customBank.trim() : bankName.trim();
    await onSubmit({
      account_holder_name: holderName.trim(),
      bank_name: effectiveBank,
      account_number: accountNumber.replace(/\s+/g, ''),
      ifsc_code: ifscCode.trim().toUpperCase(),
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:p-8 space-y-6"
      noValidate
    >
      <div className="border-b border-slate-100 pb-5">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-emerald-50 text-emerald-700 rounded-xl">
            <Building2 className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              {isReplacing ? 'Replace Payout Bank Account' : 'Direct Bank Payout Details'}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Service earnings will be disbursed directly to this verified bank account.
            </p>
          </div>
        </div>
      </div>

      {/* Security Banner */}
      <div className="p-3.5 bg-slate-50 border border-slate-200/70 rounded-xl flex items-start gap-3">
        <Lock className="w-4 h-4 text-emerald-600 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-slate-600 leading-relaxed">
          <span className="font-semibold text-slate-800">Bank-Grade Transit Encryption:</span> Full
          account numbers are directly tokenized and transmitted to our regulated payout partner
          (RazorpayX). VehicleCare only stores masked account numbers (<span className="font-mono">•••• 1234</span>).
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {/* Account Holder Name */}
        <div className="sm:col-span-2 space-y-1.5">
          <label htmlFor="holderName" className="block text-xs font-semibold text-slate-700">
            Account Holder Name (as per Bank Passbook / Pan Card) <span className="text-rose-500">*</span>
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <User className="w-4 h-4" />
            </div>
            <input
              id="holderName"
              type="text"
              value={holderName}
              onChange={(e) => {
                setHolderName(e.target.value);
                if (errors.holderName) setErrors((prev) => ({ ...prev, holderName: '' }));
              }}
              placeholder="e.g. Ramesh Kumar Verma"
              disabled={isSubmitting}
              className={`w-full pl-10 pr-3.5 py-2.5 bg-slate-50/50 border rounded-xl text-sm font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
                errors.holderName ? 'border-rose-400 bg-rose-50/30' : 'border-slate-200'
              }`}
            />
          </div>
          {errors.holderName && (
            <p className="text-xs text-rose-600 flex items-center gap-1 mt-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {errors.holderName}
            </p>
          )}
        </div>

        {/* Bank Selection */}
        <div className="space-y-1.5">
          <label htmlFor="bankName" className="block text-xs font-semibold text-slate-700">
            Bank Name <span className="text-rose-500">*</span>
          </label>
          <select
            id="bankName"
            value={bankName}
            onChange={(e) => {
              setBankName(e.target.value);
              if (errors.bankName) setErrors((prev) => ({ ...prev, bankName: '' }));
            }}
            disabled={isSubmitting}
            className={`w-full px-3.5 py-2.5 bg-slate-50/50 border rounded-xl text-sm font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
              errors.bankName ? 'border-rose-400 bg-rose-50/30' : 'border-slate-200'
            }`}
          >
            <option value="">Select your bank</option>
            {COMMON_BANKS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
            <option value="Other">Other Bank</option>
          </select>
          {bankName === 'Other' && (
            <input
              type="text"
              placeholder="Enter bank name"
              value={customBank}
              onChange={(e) => setCustomBank(e.target.value)}
              disabled={isSubmitting}
              className="mt-2 w-full px-3.5 py-2 bg-slate-50/50 border border-slate-200 rounded-xl text-sm font-medium focus:outline-none focus:border-emerald-500"
            />
          )}
          {errors.bankName && (
            <p className="text-xs text-rose-600 flex items-center gap-1 mt-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {errors.bankName}
            </p>
          )}
        </div>

        {/* IFSC Code */}
        <div className="space-y-1.5">
          <label htmlFor="ifscCode" className="block text-xs font-semibold text-slate-700">
            IFSC Code <span className="text-rose-500">*</span>
          </label>
          <div className="relative">
            <input
              id="ifscCode"
              type="text"
              maxLength={11}
              value={ifscCode}
              onChange={(e) => {
                setIfscCode(e.target.value.toUpperCase());
                if (errors.ifscCode) setErrors((prev) => ({ ...prev, ifscCode: '' }));
              }}
              placeholder="e.g. HDFC0001234"
              disabled={isSubmitting}
              className={`w-full px-3.5 py-2.5 font-mono uppercase bg-slate-50/50 border rounded-xl text-sm font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
                errors.ifscCode ? 'border-rose-400 bg-rose-50/30' : 'border-slate-200'
              }`}
            />
          </div>
          {errors.ifscCode ? (
            <p className="text-xs text-rose-600 flex items-center gap-1 mt-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {errors.ifscCode}
            </p>
          ) : (
            <p className="text-[11px] text-slate-400 mt-1">11-character alphanumeric code</p>
          )}
        </div>

        {/* Account Number */}
        <div className="space-y-1.5">
          <label htmlFor="accountNumber" className="block text-xs font-semibold text-slate-700">
            Bank Account Number <span className="text-rose-500">*</span>
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <CreditCard className="w-4 h-4" />
            </div>
            <input
              id="accountNumber"
              type="password"
              autoComplete="new-password"
              value={accountNumber}
              onChange={(e) => {
                setAccountNumber(e.target.value);
                if (errors.accountNumber) setErrors((prev) => ({ ...prev, accountNumber: '' }));
              }}
              placeholder="Enter account number"
              disabled={isSubmitting}
              className={`w-full pl-10 pr-3.5 py-2.5 font-mono bg-slate-50/50 border rounded-xl text-sm font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
                errors.accountNumber ? 'border-rose-400 bg-rose-50/30' : 'border-slate-200'
              }`}
            />
          </div>
          {errors.accountNumber && (
            <p className="text-xs text-rose-600 flex items-center gap-1 mt-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {errors.accountNumber}
            </p>
          )}
        </div>

        {/* Confirm Account Number */}
        <div className="space-y-1.5">
          <label htmlFor="confirmAccountNumber" className="block text-xs font-semibold text-slate-700">
            Re-enter Account Number <span className="text-rose-500">*</span>
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
              <CreditCard className="w-4 h-4" />
            </div>
            <input
              id="confirmAccountNumber"
              type="text"
              value={confirmAccountNumber}
              onChange={(e) => {
                setConfirmAccountNumber(e.target.value);
                if (errors.confirmAccountNumber)
                  setErrors((prev) => ({ ...prev, confirmAccountNumber: '' }));
              }}
              placeholder="Confirm account number"
              disabled={isSubmitting}
              className={`w-full pl-10 pr-3.5 py-2.5 font-mono bg-slate-50/50 border rounded-xl text-sm font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 transition ${
                errors.confirmAccountNumber ? 'border-rose-400 bg-rose-50/30' : 'border-slate-200'
              }`}
            />
          </div>
          {errors.confirmAccountNumber && (
            <p className="text-xs text-rose-600 flex items-center gap-1 mt-1">
              <AlertCircle className="w-3.5 h-3.5" />
              {errors.confirmAccountNumber}
            </p>
          )}
        </div>
      </div>

      {/* Consent Checkbox */}
      <div className="p-4 bg-slate-50/70 border border-slate-200/80 rounded-xl space-y-2">
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={consentGiven}
            onChange={(e) => {
              setConsentGiven(e.target.checked);
              if (errors.consent) setErrors((prev) => ({ ...prev, consent: '' }));
            }}
            disabled={isSubmitting}
            className="mt-0.5 h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 transition"
          />
          <span className="text-xs text-slate-600 leading-snug">
            I confirm that I am the legal owner of this bank account and authorize VehicleCare to
            disburse my earned service commissions to this account. I understand that a ₹1 penny-drop
            validation may be conducted by RazorpayX to verify beneficiary details.
          </span>
        </label>
        {errors.consent && (
          <p className="text-xs text-rose-600 flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5" />
            {errors.consent}
          </p>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-3 pt-2">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="w-full sm:w-auto px-5 py-2.5 rounded-xl border border-slate-300 text-slate-700 text-sm font-semibold hover:bg-slate-50 transition"
          >
            Cancel
          </button>
        )}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold shadow-sm hover:bg-emerald-700 focus:ring-4 focus:ring-emerald-500/20 disabled:opacity-50 transition"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Saving Account...</span>
            </>
          ) : (
            <>
              <ShieldCheck className="w-4 h-4" />
              <span>{isReplacing ? 'Replace & Save Account' : 'Save & Initiate Verification'}</span>
            </>
          )}
        </button>
      </div>
    </form>
  );
};
