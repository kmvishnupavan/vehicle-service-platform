import React, { useState } from 'react';
import {
  FileText,
  Search,
  RotateCcw,
  Clock,
  Eye,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuditLogs } from '../../hooks/useAdminOperations';
import { AuditLogItem } from '../../types/adminOperations';

export const AuditLogPage: React.FC = () => {
  const [actionFilter, setActionFilter] = useState('');
  const [entityFilter, setEntityFilter] = useState('');
  const [requestIdFilter, setRequestIdFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 25;

  const [selectedLog, setSelectedLog] = useState<AuditLogItem | null>(null);

  const {
    data: auditData,
    isLoading,
    error,
    refetch,
  } = useAuditLogs({
    action: actionFilter || undefined,
    entity_type: entityFilter || undefined,
    request_id: requestIdFilter || undefined,
    limit,
    offset,
  });

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
                <span className="text-indigo-600">Audit Logs</span>
              </div>
              <h1 className="text-xl sm:text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                <div className="p-2 bg-indigo-100/70 text-indigo-700 rounded-lg">
                  <FileText className="w-6 h-6" />
                </div>
                <span>Platform Audit & Security Event Viewer</span>
              </h1>
            </div>

            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 shadow-sm transition"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 space-y-6">
        {/* Filter Controls */}
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-sm grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div>
            <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Action Name
            </label>
            <div className="relative">
              <input
                type="text"
                value={actionFilter}
                onChange={(e) => {
                  setActionFilter(e.target.value);
                  setOffset(0);
                }}
                placeholder="e.g. payment_settled, batch_approved"
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Entity Type
            </label>
            <input
              type="text"
              value={entityFilter}
              onChange={(e) => {
                setEntityFilter(e.target.value);
                setOffset(0);
              }}
              placeholder="e.g. booking, payment, settlement_batch"
              className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Trace / Request ID
            </label>
            <input
              type="text"
              value={requestIdFilter}
              onChange={(e) => {
                setRequestIdFilter(e.target.value);
                setOffset(0);
              }}
              placeholder="e.g. UUID trace identifier"
              className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Audit Log Table */}
        <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="p-12 text-center text-slate-500 text-xs">
              <div className="w-8 h-8 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              Loading audit log records...
            </div>
          ) : error ? (
            <div className="p-6 text-center text-rose-600 text-xs bg-rose-50">
              Failed to load audit logs. Please verify administrative role access.
            </div>
          ) : !auditData || auditData.items.length === 0 ? (
            <div className="p-12 text-center text-slate-500">
              <div className="w-12 h-12 bg-slate-100 text-slate-400 rounded-2xl flex items-center justify-center mx-auto mb-3">
                <Search className="w-6 h-6" />
              </div>
              <h4 className="text-sm font-bold text-slate-800">No Audit Logs Found</h4>
              <p className="text-xs text-slate-400 max-w-sm mx-auto mt-1">
                No events matched the current filter query criteria.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50/80 text-[11px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-200/70">
                    <th className="py-3.5 px-6">Timestamp</th>
                    <th className="py-3.5 px-6">Action</th>
                    <th className="py-3.5 px-6">Entity</th>
                    <th className="py-3.5 px-6">Actor / Role</th>
                    <th className="py-3.5 px-6">Request ID</th>
                    <th className="py-3.5 px-6 text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-xs">
                  {auditData.items.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/60 transition">
                      <td className="py-4 px-6 text-slate-500 flex items-center gap-1.5 font-mono text-[11px]">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span>{new Date(log.created_at).toLocaleString()}</span>
                      </td>

                      <td className="py-4 px-6 font-bold text-slate-900">
                        <span className="font-mono text-[11px] px-2 py-0.5 bg-slate-100 rounded text-slate-800 border border-slate-200">
                          {log.action}
                        </span>
                      </td>

                      <td className="py-4 px-6">
                        <span className="font-semibold text-slate-700 capitalize">{log.entity_type}</span>
                        {log.entity_id && (
                          <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                            ID: {String(log.entity_id).slice(0, 8)}...
                          </div>
                        )}
                      </td>

                      <td className="py-4 px-6">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                          {log.actor_role || 'system'}
                        </span>
                        {log.actor_id && (
                          <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                            {String(log.actor_id).slice(0, 8)}...
                          </div>
                        )}
                      </td>

                      <td className="py-4 px-6 font-mono text-[11px] text-slate-500">
                        {log.request_id ? `${log.request_id.slice(0, 8)}...` : '—'}
                      </td>

                      <td className="py-4 px-6 text-right">
                        <button
                          type="button"
                          onClick={() => setSelectedLog(log)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-lg border border-indigo-200 transition"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>View</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination Controls */}
              <div className="p-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                <span>
                  Showing {offset + 1} to {Math.min(offset + limit, auditData.total)} of {auditData.total} logs
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setOffset((prev) => Math.max(0, prev - limit))}
                    disabled={offset === 0}
                    className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setOffset((prev) => prev + limit)}
                    disabled={offset + limit >= auditData.total}
                    className="p-1.5 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Log Detail Modal */}
      {selectedLog && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl border border-slate-100 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>Audit Event: {selectedLog.action}</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">Log ID: {selectedLog.id}</p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedLog(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-100"
              >
                ✕
              </button>
            </div>

            <div className="py-4 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-3 bg-slate-50 p-3.5 rounded-xl">
                <div>
                  <span className="text-slate-400 block">Actor Role</span>
                  <span className="font-semibold text-slate-800">{selectedLog.actor_role || 'system'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Request ID</span>
                  <span className="font-mono text-slate-800">{selectedLog.request_id || '—'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Entity</span>
                  <span className="font-semibold text-slate-800">{selectedLog.entity_type} ({String(selectedLog.entity_id || '—')})</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Recorded At</span>
                  <span className="font-medium text-slate-700">{new Date(selectedLog.created_at).toLocaleString()}</span>
                </div>
              </div>

              {/* Event Payload */}
              <div>
                <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1.5">
                  Sanitized Event Payload (new_data)
                </h4>
                <pre className="p-3 bg-slate-900 text-slate-100 rounded-xl font-mono text-[11px] overflow-x-auto">
                  {JSON.stringify(selectedLog.new_data || {}, null, 2)}
                </pre>
              </div>

              {selectedLog.old_data && (
                <div>
                  <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1.5">
                    Previous State (old_data)
                  </h4>
                  <pre className="p-3 bg-slate-100 text-slate-800 rounded-xl font-mono text-[11px] overflow-x-auto">
                    {JSON.stringify(selectedLog.old_data, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            <div className="pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={() => setSelectedLog(null)}
                className="px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-200 transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
