import React from 'react';
import { Circle, ListChecks, Check, Clock } from 'lucide-react';
import { BookingChecklistItem } from '../../types/serviceOperations';

interface Props {
  items: BookingChecklistItem[];
  onToggleItem?: (item: BookingChecklistItem) => void;
  isEditable?: boolean;
}

export const ServiceChecklistProgress: React.FC<Props> = ({
  items,
  onToggleItem,
  isEditable = false,
}) => {
  if (!items || items.length === 0) {
    return null;
  }

  const completedCount = items.filter((it) => it.is_completed).length;
  const totalCount = items.length;
  const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
            <ListChecks className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-slate-900">Service Execution Checklist</h3>
            <p className="text-2xs text-slate-500">
              {completedCount} of {totalCount} mandatory checkpoints completed
            </p>
          </div>
        </div>
        <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-100">
          {progressPercent}% Done
        </span>
      </div>

      {/* Progress Bar */}
      <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden mb-4">
        <div
          className="h-full bg-blue-600 rounded-full transition-all duration-300"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Checklist Task Items */}
      <div className="space-y-2">
        {items.map((item) => (
          <div
            key={item.id}
            onClick={() => isEditable && onToggleItem && onToggleItem(item)}
            className={`p-3 rounded-xl border transition flex items-start space-x-3 ${
              isEditable ? 'cursor-pointer hover:border-blue-300' : ''
            } ${
              item.is_completed
                ? 'bg-slate-50/60 border-slate-200 text-slate-800'
                : 'bg-white border-slate-200/90 text-slate-700'
            }`}
          >
            <div className="mt-0.5 flex-shrink-0">
              {item.is_completed ? (
                <div className="w-4 h-4 rounded-md bg-emerald-600 text-white flex items-center justify-center">
                  <Check className="w-3 h-3 stroke-[3]" />
                </div>
              ) : (
                <Circle className="w-4 h-4 text-slate-400" />
              )}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center space-x-2">
                <span
                  className={`text-xs font-medium ${
                    item.is_completed ? 'line-through text-slate-400' : 'text-slate-900'
                  }`}
                >
                  {item.title}
                </span>
                {item.is_mandatory && !item.is_completed && (
                  <span className="text-3xs px-1.5 py-0.2 rounded bg-amber-50 text-amber-700 border border-amber-200 font-semibold uppercase">
                    Mandatory
                  </span>
                )}
              </div>
              {item.notes && <p className="text-2xs text-slate-500 mt-0.5">{item.notes}</p>}
            </div>

            {item.completed_at && (
              <span className="text-3xs text-slate-400 flex items-center space-x-1 flex-shrink-0">
                <Clock className="w-2.5 h-2.5" />
                <span>{new Date(item.completed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
