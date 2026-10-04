import React, { useState } from 'react';
import {
  ShieldCheck,
  Plus,
  Sliders,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Clock,
  Layers,
  Send,
  Ban,
  Eye,
  Info,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import {
  useAdminSettlements,
  useAdminSettlementDetail,
  useSettlementPolicy,
  useUpdateSettlementPolicy,
  useCreateSettlementBatch,
  useSubmitSettlementBatch,
  useApproveSettlementBatch,
  useRejectSettlementBatch,
  useCancelSettlementBatch,
} from '../../hooks/useAdminSettlements';
import { SettlementStatusBadge } from '../../components/admin/SettlementStatusBadge';
import { SettlementApprovalModal } from '../../components/admin/SettlementApprovalModal';
import { SettlementPolicyModal } from '../../components/admin/SettlementPolicyModal';
import { SettlementBatchItem } from '../../types/settlement';

export const SettlementManagementPage: React.FC = () => {
  const { user } = useAuth();

  // Filters & pagination
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [offset, setOffset] = useState<number>(0);
  const limit = 10;

  // Selected batch for detail modal or approval actions
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [actionBatch, setActionBatch] = useState<{
    batch: SettlementBatchItem;
    action: 'approve' | 'reject';
  } | null>(null);
  const [isPolicyModalOpen, setIsPolicyModalOpen] = useState(false);

  // Queries
  const {
    data: batchesData,
    isLoading: isBatchesLoading,
    error: batchesError,
    refetch: refetchBatches,
  } = useAdminSettlements({
    status: selectedStatus,
    limit,
    offset,
  });

  const { data: batchDetail } = useAdminSettlementDetail(selectedBatchId);
  const { data: policy } = useSettlementPolicy();

  // Mutations
  const createBatchMutation = useCreateSettlementBatch();
  const submitBatchMutation = useSubmitSettlementBatch();
  const approveBatchMutation = useApproveSettlementBatch();
  const rejectBatchMutation = useRejectSettlementBatch();
  const cancelBatchMutation = useCancelSettlementBatch();
  const updatePolicyMutation = useUpdateSettlementPolicy();

  const handleCreateBatch = async () => {
    try {
      await createBatchMutation.mutateAsync();
      refetchBatches();
    } catch (err: any) {
      alert(err?.message || 'Failed to create settlement batch.');
    }
  };

  const handleSubmitForApproval = async (batchId: string) => {
    try {
      await submitBatchMutation.mutateAsync({ batchId });
      refetchBatches();
    } catch (err: any) {
      alert(err?.message || 'Failed to submit batch for approval.');
    }
  };

  const handleCancelBatch = async (batchId: string) => {
    if (!window.confirm('Are you sure you want to cancel this batch? Associated ledger items will be released.')) {
      return;
    }
    try {
      await cancelBatchMutation.mutateAsync({ batchId, reason: 'Cancelled by administrator' });
      refetchBatches();
    } catch (err: any) {
      alert(err?.message || 'Failed to cancel batch.');
    }
  };

  const handleConfirmApprovalAction = async (reason?: string) => {
    if (!actionBatch) return;
    const { batch, action } = actionBatch;
    if (action === 'approve') {
      await approveBatchMutation.mutateAsync({ batchId: batch.id, reason });
    } else {
      await rejectBatchMutation.mutateAsync({ batchId: batch.id, reason });
    }
    refetchBatches();
  };

  const handleSavePolicy = async (thresholdAmount: number, requiresChecker: boolean) => {
    await updatePolicyMutation.mutateAsync({
      threshold_amount: thresholdAmount,
      requires_checker: requiresChecker,
      is_active: true,
    });
  };

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

  return (
    <div className="min-h-screen bg-slate-50/60 pb-16">
      {/* Top Banner */}
      <div className="bg-white border-b border-slate-200/80 sticky top-16 z-10 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 sm:py-5">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 mb-1">
                <span>Administration</span>
                <span className="text-slate-300">/</span>
                <span className="text-emerald-600">Settlements</span>
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                <div className="p-2 bg-emerald-100/70 text-emerald-700 rounded-lg">
                  <ShieldCheck className="w-6 h-6" />
                </div>
                <span>Settlement Disbursements & Maker-Checker Control</span>
              </h1>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {policy && (
                <div className="hidden sm:flex items-center gap-2 text-xs font-medium text-slate-600 bg-slate-100/80 px-3 py-1.5 rounded-lg border border-slate-200">
                  <span className="text-slate-400">Threshold:</span>
                  <span className="font-bold text-slate-800">₹{policy.threshold_amount}</span>
                  <span className="text-slate-300">|</span>
                  <span className={policy.requires_checker ? 'text-amber-700' : 'text-slate-500'}>
                    {policy.requires_checker ? 'Checker Required' : 'Threshold Only'}
                  </span>
                </div>
              )}

              <button
                type="button"
                onClick={() => setIsPolicyModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-2 bg-white text-slate-700 border border-slate-300 rounded-lg text-xs font-semibold hover:bg-slate-50 shadow-sm transition"
              >
                <Sliders className="w-4 h-4 text-slate-500" />
                <span>Policy</span>
              </button>

              <button
                type="button"
                onClick={handleCreateBatch}
                disabled={createBatchMutation.isPending}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-emerald-600 text-white rounded-lg text-xs font-semibold hover:bg-emerald-700 disabled:bg-emerald-400 shadow-sm transition"
              >
                {createBatchMutation.isPending ? (
                  <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Plus className="w-4 h-4" />
                )}
                <span>Create Batch (Maker)</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {/* Status Filter Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-sm">
          <div className="flex flex-wrap items-center gap-1.5">
            {[
              { id: 'all', label: 'All Batches' },
              { id: 'approval_required', label: 'Approval Required' },
              { id: 'draft', label: 'Draft' },
              { id: 'approved', label: 'Approved' },
              { id: 'processing', label: 'Processing' },
              { id: 'completed', label: 'Completed' },
              { id: 'rejected', label: 'Rejected' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => {
                  setSelectedStatus(tab.id);
                  setOffset(0);
                }}
                className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition ${
                  selectedStatus === tab.id
                    ? 'bg-slate-900 text-white shadow-sm'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => refetchBatches()}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 px-2.5 py-1.5 hover:bg-slate-100 rounded-lg transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>

        {/* Batch Table Card */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          {isBatchesLoading ? (
            <div className="p-12 text-center text-slate-500 text-xs">
              <div className="w-8 h-8 border-3 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              Loading settlement batches...
            </div>
          ) : batchesError ? (
            <div className="p-8 text-center text-rose-600 text-xs">
              Failed to load settlement batches. Please check credentials or permissions.
            </div>
          ) : !batchesData || batchesData.items.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <div className="w-12 h-12 bg-slate-100 text-slate-400 rounded-2xl flex items-center justify-center mx-auto mb-3">
                <Layers className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-bold text-slate-800">No Settlement Batches Found</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                Click &quot;Create Batch&quot; above to aggregate all currently eligible mechanic ledger records.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                    <th className="py-3.5 px-6">Batch Reference</th>
                    <th className="py-3.5 px-6">Items</th>
                    <th className="py-3.5 px-6 text-right">Net Amount</th>
                    <th className="py-3.5 px-6">Status</th>
                    <th className="py-3.5 px-6">Maker / Created</th>
                    <th className="py-3.5 px-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-xs">
                  {batchesData.items.map((batch) => {
                    const isMaker = Boolean(user && batch.created_by && user.id === batch.created_by);
                    const canCheckerAct =
                      !isMaker && batch.status === 'approval_required';

                    return (
                      <tr key={batch.id} className="hover:bg-slate-50/60 transition">
                        <td className="py-4 px-6">
                          <button
                            type="button"
                            onClick={() => setSelectedBatchId(batch.id)}
                            className="font-mono text-xs font-bold text-slate-900 hover:text-emerald-700 flex items-center gap-1.5 text-left"
                          >
                            <span>{batch.batch_number}</span>
                            <Eye className="w-3.5 h-3.5 text-slate-400" />
                          </button>
                          <div className="text-[11px] text-slate-400 font-sans mt-0.5">
                            ID: {batch.id.slice(0, 8)}...
                          </div>
                        </td>

                        <td className="py-4 px-6 font-semibold text-slate-700">
                          {batch.item_count} {batch.item_count === 1 ? 'payout' : 'payouts'}
                        </td>

                        <td className="py-4 px-6 text-right font-extrabold text-slate-900">
                          {formatCurrency(batch.total_amount, batch.currency)}
                        </td>

                        <td className="py-4 px-6">
                          <SettlementStatusBadge status={batch.status} />
                        </td>

                        <td className="py-4 px-6">
                          <div className="flex items-center gap-1.5 font-medium text-slate-700">
                            {isMaker ? (
                              <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded text-[11px] font-semibold">
                                You (Maker)
                              </span>
                            ) : (
                              <span>Admin #{batch.created_by ? batch.created_by.slice(0, 8) : 'Sys'}</span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-400 mt-0.5">
                            {formatDate(batch.created_at)}
                          </div>
                        </td>

                        <td className="py-4 px-6 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {/* Maker Draft Submission */}
                            {batch.status === 'draft' && isMaker && (
                              <button
                                type="button"
                                onClick={() => handleSubmitForApproval(batch.id)}
                                disabled={submitBatchMutation.isPending}
                                className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-amber-600 text-white rounded text-xs font-semibold hover:bg-amber-700 transition"
                              >
                                <Send className="w-3.5 h-3.5" />
                                <span>Submit for Review</span>
                              </button>
                            )}

                            {/* Maker Self-Approval Prevention Warning */}
                            {batch.status === 'approval_required' && isMaker && (
                              <span
                                className="inline-flex items-center gap-1 px-2 py-1 bg-amber-50 text-amber-800 border border-amber-200 rounded text-[11px] font-medium"
                                title="Enforced by Maker-Checker protocol: Creators cannot approve their own batch"
                              >
                                <Info className="w-3 h-3 text-amber-600" />
                                <span>Self-Approval Restricted</span>
                              </span>
                            )}

                            {/* Checker Approval & Rejection */}
                            {canCheckerAct && (
                              <>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setActionBatch({ batch, action: 'approve' })
                                  }
                                  className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-emerald-600 text-white rounded text-xs font-semibold hover:bg-emerald-700 transition shadow-sm"
                                >
                                  <CheckCircle2 className="w-3.5 h-3.5" />
                                  <span>Approve</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setActionBatch({ batch, action: 'reject' })
                                  }
                                  className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-rose-600 text-white rounded text-xs font-semibold hover:bg-rose-700 transition shadow-sm"
                                >
                                  <XCircle className="w-3.5 h-3.5" />
                                  <span>Reject</span>
                                </button>
                              </>
                            )}

                            {/* Cancellation for draft/approved */}
                            {['draft', 'approval_required', 'approved'].includes(batch.status) && (
                              <button
                                type="button"
                                onClick={() => handleCancelBatch(batch.id)}
                                className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition"
                                title="Cancel batch & release payouts"
                              >
                                <Ban className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Batch Detail Side Drawer / Modal */}
      {selectedBatchId && batchDetail && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div>
                <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                  <span>Batch: {batchDetail.batch_number}</span>
                  <SettlementStatusBadge status={batchDetail.status} size="sm" />
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">UUID: {batchDetail.id}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedBatchId(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            <div className="py-4 space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-xl text-xs">
                <div>
                  <span className="text-slate-400 block">Total Amount</span>
                  <span className="font-extrabold text-slate-900 text-sm">
                    {formatCurrency(batchDetail.total_amount, batchDetail.currency)}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block">Total Items</span>
                  <span className="font-bold text-slate-800 text-sm">
                    {batchDetail.item_count}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block">Created At</span>
                  <span className="font-medium text-slate-700">
                    {formatDate(batchDetail.created_at)}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block">Completed At</span>
                  <span className="font-medium text-slate-700">
                    {formatDate(batchDetail.completed_at)}
                  </span>
                </div>
              </div>

              {/* Approval History Trail */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                  Maker-Checker Audit Trail
                </h4>
                {batchDetail.approvals && batchDetail.approvals.length > 0 ? (
                  <div className="space-y-2">
                    {batchDetail.approvals.map((appr) => (
                      <div
                        key={appr.id}
                        className="p-3 rounded-xl border border-slate-200/80 bg-white flex items-start justify-between text-xs"
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold uppercase tracking-wider text-[11px] text-slate-800">
                              {appr.action.replace(/_/g, ' ')}
                            </span>
                            <span className="px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded text-[10px]">
                              {appr.actor_role}
                            </span>
                          </div>
                          {appr.reason && (
                            <p className="text-slate-600 mt-1 italic text-[11px]">
                              &quot;{appr.reason}&quot;
                            </p>
                          )}
                        </div>
                        <div className="text-[11px] text-slate-400 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          <span>{formatDate(appr.created_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">No formal approval steps logged yet.</p>
                )}
              </div>
            </div>

            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedBatchId(null)}
                className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-200 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Approval Confirmation Modal */}
      {actionBatch && (
        <SettlementApprovalModal
          batch={actionBatch.batch}
          action={actionBatch.action}
          isOpen={Boolean(actionBatch)}
          onClose={() => setActionBatch(null)}
          onConfirm={handleConfirmApprovalAction}
          isLoading={approveBatchMutation.isPending || rejectBatchMutation.isPending}
        />
      )}

      {/* Policy Modal */}
      <SettlementPolicyModal
        policy={policy}
        isOpen={isPolicyModalOpen}
        onClose={() => setIsPolicyModalOpen(false)}
        onSave={handleSavePolicy}
        isLoading={updatePolicyMutation.isPending}
      />
    </div>
  );
};
