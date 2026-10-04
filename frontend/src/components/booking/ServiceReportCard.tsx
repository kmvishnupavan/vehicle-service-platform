import React from 'react';
import { FileCheck, Wrench, Receipt } from 'lucide-react';
import { ServiceReport } from '../../types/serviceOperations';

interface Props {
  report: ServiceReport;
  onViewInvoice?: () => void;
}

export const ServiceReportCard: React.FC<Props> = ({ report, onViewInvoice }) => {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-200 gap-3">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center shadow-sm">
            <FileCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-base">Official Service Report</h3>
            <p className="text-xs text-slate-500">
              Completed on {new Date(report.completed_at).toLocaleDateString()} at{' '}
              {new Date(report.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
        </div>

        {onViewInvoice && (
          <button
            onClick={onViewInvoice}
            className="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold flex items-center space-x-1.5 transition self-start sm:self-auto"
          >
            <Receipt className="w-3.5 h-3.5 text-slate-600" />
            <span>View Tax Invoice</span>
          </button>
        )}
      </div>

      <div className="mt-5 space-y-5 text-sm">
        {/* Work Performed Summary */}
        <div>
          <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">
            Work Performed Summary
          </h4>
          <p className="text-sm font-semibold text-slate-900">{report.summary}</p>
          <div className="mt-2 p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 whitespace-pre-line leading-relaxed">
            {report.work_performed}
          </div>
        </div>

        {/* Parts Installed */}
        {report.parts_used && report.parts_used.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center space-x-1.5">
              <Wrench className="w-3.5 h-3.5" />
              <span>Replacement Parts Installed ({report.parts_used.length})</span>
            </h4>
            <div className="space-y-1.5">
              {report.parts_used.map((part, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg border border-slate-200 bg-slate-50/50 flex justify-between items-center text-xs"
                >
                  <div>
                    <span className="font-semibold text-slate-900">{part.part_name}</span>
                    {part.part_number && (
                      <span className="text-slate-500 ml-1.5 font-mono text-2xs">({part.part_number})</span>
                    )}
                    {part.warranty_months && (
                      <span className="text-2xs text-emerald-700 ml-2 font-medium">
                        • {part.warranty_months}m warranty
                      </span>
                    )}
                  </div>
                  <span className="font-semibold text-slate-900">
                    {part.quantity} × ₹{Number(part.unit_price).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Future Recommendations */}
        {report.recommendations && (
          <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-200 text-xs">
            <h5 className="font-semibold text-blue-900 mb-1">Technician Recommendations for Next Service</h5>
            <p className="text-blue-800 leading-relaxed">{report.recommendations}</p>
          </div>
        )}

        {/* Final Financial Totals */}
        {report.final_totals && (
          <div className="pt-3 border-t border-slate-200 flex justify-between items-center text-sm">
            <span className="font-medium text-slate-600">Final Total Billed</span>
            <span className="text-base font-bold text-slate-900">
              ₹{Number(report.final_totals.total_amount || 0).toFixed(2)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
