import React from 'react';
import { Filter, Calendar, RotateCcw } from 'lucide-react';

export type PayoutStatusFilter = 'all' | 'eligible' | 'pending' | 'processing' | 'paid' | 'reversed';
export type DatePreset = 'all' | 'today' | 'this_week' | 'this_month' | 'custom';

interface PayoutFiltersProps {
  selectedStatus: PayoutStatusFilter;
  onStatusChange: (status: PayoutStatusFilter) => void;
  selectedPreset: DatePreset;
  fromDate?: string;
  toDate?: string;
  onDateChange: (preset: DatePreset, from?: string, to?: string) => void;
  onRefresh: () => void;
  isLoading?: boolean;
}

export const PayoutFilters: React.FC<PayoutFiltersProps> = ({
  selectedStatus,
  onStatusChange,
  selectedPreset,
  fromDate,
  toDate,
  onDateChange,
  onRefresh,
  isLoading = false,
}) => {
  const statusOptions: { label: string; value: PayoutStatusFilter }[] = [
    { label: 'All Payouts', value: 'all' },
    { label: 'Eligible', value: 'eligible' },
    { label: 'Pending', value: 'pending' },
    { label: 'Processing', value: 'processing' },
    { label: 'Paid & Settled', value: 'paid' },
    { label: 'Reversed', value: 'reversed' },
  ];

  const handlePresetSelect = (preset: DatePreset) => {
    if (preset === 'all') {
      onDateChange('all', undefined, undefined);
      return;
    }

    const now = new Date();
    const toStr = now.toISOString().split('T')[0];

    if (preset === 'today') {
      onDateChange('today', toStr, toStr);
    } else if (preset === 'this_week') {
      const day = now.getDay();
      const diff = now.getDate() - day + (day === 0 ? -6 : 1);
      const monday = new Date(now.setDate(diff));
      onDateChange('this_week', monday.toISOString().split('T')[0], toStr);
    } else if (preset === 'this_month') {
      const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
      onDateChange('this_month', firstDay.toISOString().split('T')[0], toStr);
    } else {
      onDateChange('custom', fromDate, toDate);
    }
  };

  return (
    <div className="bg-white rounded-xl p-4 border border-slate-200/80 shadow-sm space-y-4">
      {/* Top Bar: Status tabs + Refresh */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Status Filter Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 scrollbar-none">
          <Filter className="w-4 h-4 text-slate-400 mr-1 flex-shrink-0" />
          {statusOptions.map((opt) => {
            const isSelected = selectedStatus === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => onStatusChange(opt.value)}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
                  isSelected
                    ? 'bg-slate-900 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200/70 hover:text-slate-900'
                }`}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        {/* Refresh Action */}
        <div className="flex items-center gap-2 self-end md:self-auto">
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-700 hover:text-slate-900 bg-slate-100 hover:bg-slate-200/80 transition disabled:opacity-50"
            title="Refresh Payout Ledger"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Date Range Selector */}
      <div className="pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Calendar className="w-3.5 h-3.5 text-slate-400 mr-1" />
          {(['all', 'today', 'this_week', 'this_month', 'custom'] as DatePreset[]).map((p) => {
            const isSelected = selectedPreset === p;
            const labels: Record<DatePreset, string> = {
              all: 'All Time',
              today: 'Today',
              this_week: 'This Week',
              this_month: 'This Month',
              custom: 'Custom Range',
            };
            return (
              <button
                key={p}
                onClick={() => handlePresetSelect(p)}
                className={`px-2.5 py-1 rounded-md transition ${
                  isSelected
                    ? 'bg-emerald-100 text-emerald-800 font-semibold'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                {labels[p]}
              </button>
            );
          })}
        </div>

        {selectedPreset === 'custom' && (
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={fromDate || ''}
              onChange={(e) => onDateChange('custom', e.target.value, toDate)}
              className="px-2.5 py-1 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
            <span className="text-slate-400">to</span>
            <input
              type="date"
              value={toDate || ''}
              onChange={(e) => onDateChange('custom', fromDate, e.target.value)}
              className="px-2.5 py-1 text-xs border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
        )}
      </div>
    </div>
  );
};
