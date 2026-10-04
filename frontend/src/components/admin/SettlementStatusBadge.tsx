import React from 'react';
import {
  FileText,
  Clock,
  CheckCircle2,
  XCircle,
  Send,
  Loader2,
  AlertTriangle,
  Ban,
} from 'lucide-react';
import { SettlementBatchStatus } from '../../types/settlement';

interface SettlementStatusBadgeProps {
  status: SettlementBatchStatus | string;
  size?: 'sm' | 'md';
}

export interface StatusConfig {
  label: string;
  sublabel?: string;
  bg: string;
  text: string;
  border: string;
  icon: React.ReactNode;
}

export const STATUS_CONFIGS: Record<string, StatusConfig> = {
  draft: {
    label: 'Draft Batch',
    sublabel: 'Awaiting submission',
    bg: 'bg-slate-100',
    text: 'text-slate-700',
    border: 'border-slate-200',
    icon: <FileText className="w-3.5 h-3.5 text-slate-500" />,
  },
  approval_required: {
    label: 'Approval Required',
    sublabel: 'Pending Checker Review',
    bg: 'bg-amber-50',
    text: 'text-amber-800',
    border: 'border-amber-200',
    icon: <Clock className="w-3.5 h-3.5 text-amber-600 animate-pulse" />,
  },
  approved: {
    label: 'Approved',
    sublabel: 'Eligible for disbursement',
    bg: 'bg-emerald-50',
    text: 'text-emerald-800',
    border: 'border-emerald-200',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />,
  },
  rejected: {
    label: 'Rejected',
    sublabel: 'Returned by Checker',
    bg: 'bg-rose-50',
    text: 'text-rose-800',
    border: 'border-rose-200',
    icon: <XCircle className="w-3.5 h-3.5 text-rose-600" />,
  },
  submitted: {
    label: 'Submitted',
    sublabel: 'Sent to RazorpayX',
    bg: 'bg-sky-50',
    text: 'text-sky-800',
    border: 'border-sky-200',
    icon: <Send className="w-3.5 h-3.5 text-sky-600" />,
  },
  processing: {
    label: 'Processing',
    sublabel: 'Bank clearinghouse',
    bg: 'bg-indigo-50',
    text: 'text-indigo-800',
    border: 'border-indigo-200',
    icon: <Loader2 className="w-3.5 h-3.5 text-indigo-600 animate-spin" />,
  },
  completed: {
    label: 'Disbursed',
    sublabel: 'Credited to account',
    bg: 'bg-emerald-100',
    text: 'text-emerald-900',
    border: 'border-emerald-300',
    icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-700" />,
  },
  partially_failed: {
    label: 'Partially Failed',
    sublabel: 'Some items bounced',
    bg: 'bg-orange-50',
    text: 'text-orange-800',
    border: 'border-orange-200',
    icon: <AlertTriangle className="w-3.5 h-3.5 text-orange-600" />,
  },
  failed: {
    label: 'Failed',
    sublabel: 'Disbursement aborted',
    bg: 'bg-rose-100',
    text: 'text-rose-900',
    border: 'border-rose-300',
    icon: <AlertTriangle className="w-3.5 h-3.5 text-rose-700" />,
  },
  cancelled: {
    label: 'Cancelled',
    sublabel: 'Batch voided',
    bg: 'bg-slate-100',
    text: 'text-slate-600',
    border: 'border-slate-300',
    icon: <Ban className="w-3.5 h-3.5 text-slate-500" />,
  },
};

export function getSettlementStatusConfig(status: SettlementBatchStatus | string): StatusConfig {
  const normStatus = String(status || '').toLowerCase();
  return (
    STATUS_CONFIGS[normStatus] || {
      label: normStatus || 'Unknown',
      bg: 'bg-slate-100',
      text: 'text-slate-700',
      border: 'border-slate-200',
      icon: null,
    }
  );
}

export const SettlementStatusBadge: React.FC<SettlementStatusBadgeProps> = ({
  status,
  size = 'md',
}) => {
  const normStatus = String(status || '').toLowerCase();
  const config = getSettlementStatusConfig(normStatus);

  const isSmall = size === 'sm';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold border ${config.bg} ${config.text} ${config.border} ${
        isSmall ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs'
      }`}
      title={config.sublabel}
    >
      {config.icon}
      <span>{config.label}</span>
    </span>
  );
};
