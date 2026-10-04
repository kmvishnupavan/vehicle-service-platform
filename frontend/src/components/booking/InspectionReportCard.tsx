import React, { useState } from 'react';
import {
  ClipboardCheck,
  FileText,
  Gauge,
  Wrench,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
} from 'lucide-react';
import { StructuredInspection } from '../../types/serviceOperations';

interface Props {
  inspection: StructuredInspection;
  onOpenApproval?: () => void;
  showApprovalCta?: boolean;
}

export const InspectionReportCard: React.FC<Props> = ({
  inspection,
  onOpenApproval,
  showApprovalCta = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const getSeverityBadge = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 'bg-red-100 text-red-800 border-red-200';
      case 'high':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800 border-yellow-200';
      default:
        return 'bg-blue-100 text-blue-800 border-blue-200';
    }
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden mb-6">
      {/* Header */}
      <div className="p-5 bg-gradient-to-r from-slate-50 to-slate-100/50 border-b border-slate-200 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center shadow-sm">
            <ClipboardCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900 text-base">Vehicle Inspection Report</h3>
            <p className="text-xs text-slate-500">Diagnostic summary submitted by certified technician</p>
          </div>
        </div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-200 transition"
          aria-label="Toggle inspection details"
        >
          {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
      </div>

      {isExpanded && (
        <div className="p-5 space-y-6">
          {/* Key Metrics Banner */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-medium text-slate-500 block mb-1">Overall Condition</span>
              <span className="text-sm font-bold text-slate-900 capitalize">
                {inspection.vehicle_condition || 'Inspected'}
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
              <div className="flex items-center space-x-1 text-slate-500 mb-1">
                <Gauge className="w-3.5 h-3.5" />
                <span className="text-xs font-medium">Odometer</span>
              </div>
              <span className="text-sm font-bold text-slate-900">
                {inspection.odometer_reading ? `${inspection.odometer_reading.toLocaleString()} km` : 'Not recorded'}
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200/80">
              <span className="text-xs font-medium text-slate-500 block mb-1">Recommended Work</span>
              <span className="text-sm font-bold text-slate-900">
                ₹{Number(inspection.estimated_additional_cost || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
          </div>

          {/* Diagnostic Findings */}
          <div>
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center space-x-1.5">
              <FileText className="w-3.5 h-3.5" />
              <span>Diagnostic Findings & Technician Notes</span>
            </h4>
            <div className="p-4 rounded-xl bg-slate-50/70 border border-slate-200 text-sm text-slate-800 whitespace-pre-line leading-relaxed">
              {inspection.findings}
            </div>
          </div>

          {/* Structured Issues List */}
          {inspection.diagnostic_findings && inspection.diagnostic_findings.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2.5">
                Issues Identified ({inspection.diagnostic_findings.length})
              </h4>
              <div className="space-y-2">
                {inspection.diagnostic_findings.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-slate-200 bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-2 shadow-xs"
                  >
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                          [{item.category}]
                        </span>
                        <span className="text-sm font-medium text-slate-900">{item.finding}</span>
                      </div>
                      {item.recommended_action && (
                        <p className="text-xs text-slate-500 mt-1">Action: {item.recommended_action}</p>
                      )}
                    </div>
                    <span
                      className={`self-start sm:self-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getSeverityBadge(
                        item.severity
                      )}`}
                    >
                      {item.severity.toUpperCase()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Recommended Additional Work */}
          {inspection.recommended_services && inspection.recommended_services.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2.5 flex items-center space-x-1.5">
                <Wrench className="w-3.5 h-3.5" />
                <span>Recommended Services & Parts</span>
              </h4>
              <div className="space-y-2">
                {inspection.recommended_services.map((rec, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-amber-200/80 bg-amber-50/40 flex items-center justify-between"
                  >
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-semibold text-slate-900">{rec.title}</span>
                        <span
                          className={`text-2xs px-2 py-0.5 rounded-md font-semibold ${
                            rec.is_required
                              ? 'bg-red-100 text-red-700'
                              : 'bg-slate-200 text-slate-700'
                          }`}
                        >
                          {rec.is_required ? 'MANDATORY' : 'OPTIONAL'}
                        </span>
                      </div>
                      {rec.description && <p className="text-xs text-slate-600 mt-0.5">{rec.description}</p>}
                    </div>
                    <div className="text-right flex-shrink-0">
                      <span className="text-sm font-bold text-slate-900">
                        ₹{Number(rec.estimated_price).toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evidence Photos */}
          {inspection.evidence_file_paths && inspection.evidence_file_paths.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center space-x-1.5">
                <ImageIcon className="w-3.5 h-3.5" />
                <span>Inspection Evidence Photos ({inspection.evidence_file_paths.length})</span>
              </h4>
              <div className="flex flex-wrap gap-2">
                {inspection.evidence_file_paths.map((path, idx) => (
                  <div
                    key={idx}
                    className="px-3 py-1.5 rounded-lg bg-slate-100 border border-slate-200 text-xs text-slate-700 flex items-center space-x-1.5"
                  >
                    <ImageIcon className="w-3.5 h-3.5 text-slate-500" />
                    <span className="font-mono">{path.split('/').pop()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Customer Approval CTA */}
          {showApprovalCta && onOpenApproval && (
            <div className="pt-2">
              <button
                onClick={onOpenApproval}
                className="w-full py-3 px-4 rounded-xl bg-blue-600 text-white font-semibold text-sm hover:bg-blue-700 transition flex items-center justify-center space-x-2 shadow-sm"
              >
                <span>Review Estimate & Authorize Repairs</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
