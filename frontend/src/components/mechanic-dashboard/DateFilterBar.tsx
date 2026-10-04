import React, { useState } from 'react';
import { Filter } from 'lucide-react';
import { DateFilterPreset } from '../../types/mechanic-dashboard';

interface DateFilterBarProps {
  currentPreset: DateFilterPreset;
  fromDate?: string;
  toDate?: string;
  onFilterChange: (preset: DateFilterPreset, fromDate?: string, toDate?: string) => void;
}

export const DateFilterBar: React.FC<DateFilterBarProps> = ({
  currentPreset,
  fromDate,
  toDate,
  onFilterChange,
}) => {
  const [showCustom, setShowCustom] = useState(currentPreset === 'custom');
  const [customFrom, setCustomFrom] = useState(fromDate || '');
  const [customTo, setCustomTo] = useState(toDate || '');

  const formatDateToYYYYMMDD = (d: Date): string => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  const handlePresetClick = (preset: DateFilterPreset) => {
    const today = new Date();
    const todayStr = formatDateToYYYYMMDD(today);

    if (preset === 'today') {
      setShowCustom(false);
      onFilterChange('today', todayStr, todayStr);
    } else if (preset === '7d') {
      setShowCustom(false);
      const past7 = new Date();
      past7.setDate(today.getDate() - 7);
      onFilterChange('7d', formatDateToYYYYMMDD(past7), todayStr);
    } else if (preset === '30d') {
      setShowCustom(false);
      const past30 = new Date();
      past30.setDate(today.getDate() - 30);
      onFilterChange('30d', formatDateToYYYYMMDD(past30), todayStr);
    } else if (preset === 'month') {
      setShowCustom(false);
      const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
      onFilterChange('month', formatDateToYYYYMMDD(firstDay), todayStr);
    } else if (preset === 'all') {
      setShowCustom(false);
      onFilterChange('all', undefined, undefined);
    } else if (preset === 'custom') {
      setShowCustom(true);
    }
  };

  const handleCustomApply = (e: React.FormEvent) => {
    e.preventDefault();
    if (customFrom && customTo) {
      onFilterChange('custom', customFrom, customTo);
    }
  };

  return (
    <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm mb-8 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center space-x-2 text-xs font-semibold text-slate-700">
          <Filter className="w-4 h-4 text-emerald-600" />
          <span>Date Filter:</span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 bg-slate-100 p-1 rounded-xl text-xs font-medium text-slate-600">
          <button
            onClick={() => handlePresetClick('all')}
            className={`px-3 py-1.5 rounded-lg transition ${
              currentPreset === 'all'
                ? 'bg-white text-slate-900 font-bold shadow-xs'
                : 'hover:text-slate-900'
            }`}
          >
            All Time
          </button>
          <button
            onClick={() => handlePresetClick('today')}
            className={`px-3 py-1.5 rounded-lg transition ${
              currentPreset === 'today'
                ? 'bg-white text-slate-900 font-bold shadow-xs'
                : 'hover:text-slate-900'
            }`}
          >
            Today
          </button>
          <button
            onClick={() => handlePresetClick('7d')}
            className={`px-3 py-1.5 rounded-lg transition ${
              currentPreset === '7d'
                ? 'bg-white text-slate-900 font-bold shadow-xs'
                : 'hover:text-slate-900'
            }`}
          >
            7 Days
          </button>
          <button
            onClick={() => handlePresetClick('30d')}
            className={`px-3 py-1.5 rounded-lg transition ${
              currentPreset === '30d'
                ? 'bg-white text-slate-900 font-bold shadow-xs'
                : 'hover:text-slate-900'
            }`}
          >
            30 Days
          </button>
          <button
            onClick={() => handlePresetClick('month')}
            className={`px-3 py-1.5 rounded-lg transition ${
              currentPreset === 'month'
                ? 'bg-white text-slate-900 font-bold shadow-xs'
                : 'hover:text-slate-900'
            }`}
          >
            This Month
          </button>
          <button
            onClick={() => handlePresetClick('custom')}
            className={`px-3 py-1.5 rounded-lg transition ${
              currentPreset === 'custom'
                ? 'bg-white text-slate-900 font-bold shadow-xs'
                : 'hover:text-slate-900'
            }`}
          >
            Custom Range
          </button>
        </div>
      </div>

      {showCustom && (
        <form
          onSubmit={handleCustomApply}
          className="pt-3 border-t border-slate-100 flex flex-wrap items-center gap-3 text-xs"
        >
          <div className="flex items-center space-x-2">
            <span className="text-slate-500 font-medium">From:</span>
            <input
              type="date"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
              className="px-2.5 py-1.5 border border-slate-200 rounded-lg text-slate-800 text-xs focus:ring-1 focus:ring-emerald-500 outline-none"
              required
            />
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-slate-500 font-medium">To:</span>
            <input
              type="date"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
              className="px-2.5 py-1.5 border border-slate-200 rounded-lg text-slate-800 text-xs focus:ring-1 focus:ring-emerald-500 outline-none"
              required
            />
          </div>
          <button
            type="submit"
            className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-lg shadow-xs transition"
          >
            Apply Range
          </button>
        </form>
      )}
    </div>
  );
};
