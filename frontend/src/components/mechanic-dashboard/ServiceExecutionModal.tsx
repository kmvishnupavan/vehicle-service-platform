import React, { useState, useEffect } from 'react';
import {
  Wrench,
  X,
  CheckCircle2,
  AlertCircle,
  Check,
  Circle,
} from 'lucide-react';
import { api } from '../../lib/api';
import { BookingChecklistItem, BookingPart } from '../../types/serviceOperations';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  bookingId: string;
  bookingNumber: string;
  bookingStatus: string;
  onRefresh: () => void;
}

export const ServiceExecutionModal: React.FC<Props> = ({
  isOpen,
  onClose,
  bookingId,
  bookingNumber,
  bookingStatus,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<'inspection' | 'checklist' | 'parts' | 'complete'>(
    bookingStatus === 'mechanic_arrived' || bookingStatus === 'inspection'
      ? 'inspection'
      : 'checklist'
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Inspection State
  const [odometer, setOdometer] = useState<number>(45000);
  const [condition, setCondition] = useState('Good');
  const [findings, setFindings] = useState('');
  const [recTitle, setRecTitle] = useState('');
  const [recPrice, setRecPrice] = useState<number>(0);
  const [isRecRequired, setIsRecRequired] = useState(true);

  // Checklist State
  const [checklist, setChecklist] = useState<BookingChecklistItem[]>([]);

  // Parts State
  const [parts, setParts] = useState<BookingPart[]>([]);
  const [newPartName, setNewPartName] = useState('');
  const [newPartNumber, setNewPartNumber] = useState('');
  const [newPartQty, setNewPartQty] = useState(1);
  const [newPartPrice, setNewPartPrice] = useState(0);

  // Completion State
  const [completionSummary, setCompletionSummary] = useState('');
  const [workPerformed, setWorkPerformed] = useState('');
  const [completionEvidencePath, setCompletionEvidencePath] = useState('');

  // Fetch checklist and parts when modal opens
  useEffect(() => {
    if (!isOpen || !bookingId) return;

    api
      .get<BookingChecklistItem[]>(`/bookings/${bookingId}/checklist`)
      .then((data) => setChecklist(data || []))
      .catch(() => {});

    api
      .get<BookingPart[]>(`/bookings/${bookingId}/parts`)
      .then((data) => setParts(data || []))
      .catch(() => {});
  }, [isOpen, bookingId]);

  if (!isOpen) return null;

  // Handlers
  const handleSubmitInspection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!findings.trim()) {
      setError('Please provide inspection findings.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const payload: any = {
        findings: findings.trim(),
        vehicle_condition: condition,
        odometer_reading: odometer,
        checklist_results: { overall_check: 'completed' },
        diagnostic_findings: [],
        recommended_services: recTitle
          ? [
              {
                title: recTitle.trim(),
                is_required: isRecRequired,
                estimated_price: recPrice,
              },
            ]
          : [],
        estimated_additional_cost: recPrice || 0,
        evidence_file_paths: [],
      };

      await api.post(`/bookings/${bookingId}/structured-inspection`, payload);
      setSuccess('Inspection submitted successfully! Estimate routed for customer approval.');
      onRefresh();
      setTimeout(() => {
        setSuccess(null);
        setActiveTab('checklist');
      }, 1500);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to submit inspection.');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleChecklist = async (item: BookingChecklistItem) => {
    try {
      const updated = await api.patch<BookingChecklistItem>(
        `/bookings/${bookingId}/checklist/${item.id}`,
        { is_completed: !item.is_completed }
      );
      setChecklist((prev) => prev.map((it) => (it.id === item.id ? updated : it)));
    } catch (err: any) {
      setError('Failed to update checklist item.');
    }
  };

  const handleAddPart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPartName.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const created = await api.post<BookingPart>(`/bookings/${bookingId}/parts`, {
        part_name: newPartName.trim(),
        part_number: newPartNumber.trim() || undefined,
        quantity: newPartQty,
        unit_price: newPartPrice,
      });
      setParts((prev) => [...prev, created]);
      setNewPartName('');
      setNewPartNumber('');
      setNewPartPrice(0);
      setNewPartQty(1);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to record part.');
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteService = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!completionSummary.trim() || !workPerformed.trim()) {
      setError('Please provide service summary and description of work performed.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await api.post(`/bookings/${bookingId}/complete`, {
        summary: completionSummary.trim(),
        work_performed: workPerformed.trim(),
        completion_evidence_paths: completionEvidencePath
          ? [completionEvidencePath.trim()]
          : [`${bookingId}/completion/verified_service.jpg`],
      });
      setSuccess('Service finalized and official report generated! Invoice issued.');
      onRefresh();
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to complete service.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-2xl w-full shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="p-4 bg-slate-900 text-white flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center">
              <Wrench className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-bold text-sm">Mechanic Service Workbench</h3>
              <p className="text-2xs text-slate-400 font-mono">{bookingNumber}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-200 bg-slate-50 text-xs font-semibold">
          <button
            onClick={() => setActiveTab('inspection')}
            className={`flex-1 py-3 text-center border-b-2 transition ${
              activeTab === 'inspection'
                ? 'border-blue-600 text-blue-600 bg-white font-bold'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            1. Inspection
          </button>
          <button
            onClick={() => setActiveTab('checklist')}
            className={`flex-1 py-3 text-center border-b-2 transition ${
              activeTab === 'checklist'
                ? 'border-blue-600 text-blue-600 bg-white font-bold'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            2. Checklist ({checklist.filter((c) => c.is_completed).length}/{checklist.length})
          </button>
          <button
            onClick={() => setActiveTab('parts')}
            className={`flex-1 py-3 text-center border-b-2 transition ${
              activeTab === 'parts'
                ? 'border-blue-600 text-blue-600 bg-white font-bold'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            3. Parts ({parts.length})
          </button>
          <button
            onClick={() => setActiveTab('complete')}
            className={`flex-1 py-3 text-center border-b-2 transition ${
              activeTab === 'complete'
                ? 'border-blue-600 text-blue-600 bg-white font-bold'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            4. Finalize
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
              <span>{success}</span>
            </div>
          )}

          {/* TAB 1: Inspection */}
          {activeTab === 'inspection' && (
            <form onSubmit={handleSubmitInspection} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-2xs font-bold text-slate-600 uppercase block mb-1">
                    Odometer (km)
                  </label>
                  <input
                    type="number"
                    value={odometer}
                    onChange={(e) => setOdometer(Number(e.target.value))}
                    className="w-full text-xs p-2.5 rounded-lg border border-slate-300"
                    required
                  />
                </div>
                <div>
                  <label className="text-2xs font-bold text-slate-600 uppercase block mb-1">
                    Overall Condition
                  </label>
                  <select
                    value={condition}
                    onChange={(e) => setCondition(e.target.value)}
                    className="w-full text-xs p-2.5 rounded-lg border border-slate-300"
                  >
                    <option value="Excellent">Excellent</option>
                    <option value="Good">Good</option>
                    <option value="Fair">Fair - Needs Attention</option>
                    <option value="Poor">Poor - Urgent Repairs</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-2xs font-bold text-slate-600 uppercase block mb-1">
                  Diagnostic Findings & Observations *
                </label>
                <textarea
                  value={findings}
                  onChange={(e) => setFindings(e.target.value)}
                  placeholder="Record brake pad wear, fluid status, diagnostic scan findings..."
                  rows={3}
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300"
                  required
                />
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                <span className="text-2xs font-bold text-slate-700 uppercase block">
                  Recommended Additional Work (Optional)
                </span>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Service title (e.g. Brake Rotor Resurfacing)"
                    value={recTitle}
                    onChange={(e) => setRecTitle(e.target.value)}
                    className="text-xs p-2 rounded-lg border border-slate-300 col-span-2 sm:col-span-1"
                  />
                  <input
                    type="number"
                    placeholder="Price in ₹"
                    value={recPrice || ''}
                    onChange={(e) => setRecPrice(Number(e.target.value))}
                    className="text-xs p-2 rounded-lg border border-slate-300 col-span-2 sm:col-span-1"
                  />
                </div>
                <label className="flex items-center space-x-2 text-2xs text-slate-600 cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={isRecRequired}
                    onChange={(e) => setIsRecRequired(e.target.checked)}
                    className="rounded text-blue-600"
                  />
                  <span>Mandatory fix (critical for vehicle safety)</span>
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-xl bg-blue-600 text-white font-bold text-xs hover:bg-blue-700 transition"
              >
                {loading ? 'Submitting...' : 'Submit Diagnostic Inspection'}
              </button>
            </form>
          )}

          {/* TAB 2: Checklist */}
          {activeTab === 'checklist' && (
            <div className="space-y-3">
              <p className="text-xs text-slate-500">
                Click items to toggle completion. All mandatory checkpoints must be checked before service completion.
              </p>
              <div className="space-y-2">
                {checklist.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleToggleChecklist(item)}
                    className={`p-3 rounded-xl border flex items-center justify-between cursor-pointer transition ${
                      item.is_completed
                        ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900'
                        : 'bg-white border-slate-200 text-slate-800 hover:border-blue-300'
                    }`}
                  >
                    <div className="flex items-center space-x-2.5">
                      {item.is_completed ? (
                        <div className="w-5 h-5 rounded-md bg-emerald-600 text-white flex items-center justify-center">
                          <Check className="w-3.5 h-3.5 stroke-[3]" />
                        </div>
                      ) : (
                        <Circle className="w-5 h-5 text-slate-400" />
                      )}
                      <div>
                        <span className="text-xs font-semibold">{item.title}</span>
                        <span className="text-3xs block text-slate-500 uppercase">{item.category_slug}</span>
                      </div>
                    </div>
                    {item.is_mandatory && (
                      <span className="text-3xs font-bold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
                        MANDATORY
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 3: Parts Tracking */}
          {activeTab === 'parts' && (
            <div className="space-y-4">
              <form onSubmit={handleAddPart} className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                <span className="text-2xs font-bold text-slate-700 uppercase block">Record Installed Part</span>
                <div className="grid grid-cols-2 gap-2">
                  <input
                    type="text"
                    placeholder="Part Name (e.g. Ceramic Brake Pads Set)"
                    value={newPartName}
                    onChange={(e) => setNewPartName(e.target.value)}
                    className="text-xs p-2 rounded-lg border border-slate-300 col-span-2"
                    required
                  />
                  <input
                    type="text"
                    placeholder="Part Number (optional)"
                    value={newPartNumber}
                    onChange={(e) => setNewPartNumber(e.target.value)}
                    className="text-xs p-2 rounded-lg border border-slate-300"
                  />
                  <div className="grid grid-cols-2 gap-1">
                    <input
                      type="number"
                      placeholder="Qty"
                      min={1}
                      value={newPartQty}
                      onChange={(e) => setNewPartQty(Number(e.target.value))}
                      className="text-xs p-2 rounded-lg border border-slate-300"
                      required
                    />
                    <input
                      type="number"
                      placeholder="₹ Price"
                      min={0}
                      value={newPartPrice || ''}
                      onChange={(e) => setNewPartPrice(Number(e.target.value))}
                      className="text-xs p-2 rounded-lg border border-slate-300"
                      required
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-2 rounded-lg bg-slate-800 text-white font-semibold text-xs hover:bg-slate-900 transition"
                >
                  + Add Part
                </button>
              </form>

              <div className="space-y-1.5">
                {parts.map((p) => (
                  <div
                    key={p.id}
                    className="p-3 rounded-lg border border-slate-200 bg-white flex justify-between items-center text-xs"
                  >
                    <div>
                      <span className="font-semibold text-slate-900">{p.part_name}</span>
                      {p.part_number && <span className="text-slate-400 ml-1.5 font-mono text-2xs">({p.part_number})</span>}
                    </div>
                    <span className="font-bold text-slate-900">
                      {p.quantity} × ₹{Number(p.unit_price).toFixed(2)} = ₹{Number(p.total_price).toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* TAB 4: Finalize Service */}
          {activeTab === 'complete' && (
            <form onSubmit={handleCompleteService} className="space-y-4">
              <div>
                <label className="text-2xs font-bold text-slate-600 uppercase block mb-1">
                  Summary of Completed Service *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Standard periodic service and front brake pad replacement"
                  value={completionSummary}
                  onChange={(e) => setCompletionSummary(e.target.value)}
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300"
                  required
                />
              </div>

              <div>
                <label className="text-2xs font-bold text-slate-600 uppercase block mb-1">
                  Detailed Work Performed *
                </label>
                <textarea
                  placeholder="Detail fluids replaced, torque values verified, test drive results..."
                  value={workPerformed}
                  onChange={(e) => setWorkPerformed(e.target.value)}
                  rows={4}
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300"
                  required
                />
              </div>

              <div>
                <label className="text-2xs font-bold text-slate-600 uppercase block mb-1">
                  Completion Proof Evidence Path (optional)
                </label>
                <input
                  type="text"
                  placeholder={`${bookingId}/completion/after_repair.jpg`}
                  value={completionEvidencePath}
                  onChange={(e) => setCompletionEvidencePath(e.target.value)}
                  className="w-full text-xs p-2.5 rounded-lg border border-slate-300 font-mono"
                />
              </div>

              <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-800">
                Notice: Completing this service triggers official service report generation, issues the final tax invoice, and invites the customer for review and payment.
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs transition shadow-sm"
              >
                {loading ? 'Finalizing...' : 'Complete Service & Issue Report'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
