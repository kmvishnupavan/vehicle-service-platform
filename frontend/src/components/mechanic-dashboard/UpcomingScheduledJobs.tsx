import React from 'react';
import {
  Calendar,
  Clock,
  MapPin,
  Wrench,
  AlertCircle,
} from 'lucide-react';
import { useMechanicScheduledJobs } from '../../hooks/useOperationalAutomation';

export const UpcomingScheduledJobs: React.FC = () => {
  const { data: jobs, isLoading, error } = useMechanicScheduledJobs();

  if (isLoading) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <div className="animate-pulse space-y-4">
          <div className="h-5 bg-slate-200 rounded-md w-1/3"></div>
          <div className="h-20 bg-slate-100 rounded-xl"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <div className="flex items-center space-x-2 text-rose-600 text-xs font-semibold">
          <AlertCircle className="w-4 h-4" />
          <span>Could not load upcoming scheduled jobs.</span>
        </div>
      </div>
    );
  }

  const scheduledList = jobs || [];

  return (
    <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
            <Calendar className="w-4 h-4" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-sm">Upcoming Scheduled Appointments</h3>
            <p className="text-[11px] text-slate-500">
              Future vehicle services and advance dispatch preparation
            </p>
          </div>
        </div>
        <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
          {scheduledList.length} Upcoming
        </span>
      </div>

      {scheduledList.length === 0 ? (
        <div className="text-center py-6 text-slate-500 bg-slate-50 rounded-xl border border-slate-100">
          <Clock className="w-8 h-8 text-slate-400 mx-auto mb-1.5" />
          <p className="text-xs font-semibold text-slate-700">No scheduled appointments assigned yet</p>
          <p className="text-[11px] text-slate-400 mt-0.5">
            When customers book advance doorstep visits, they will appear here with tool checklists.
          </p>
        </div>
      ) : (
        <div className="space-y-3.5">
          {scheduledList.map((job: any) => {
            const scheduledDate = job.scheduled_at
              ? new Date(job.scheduled_at)
              : null;
            const isToday =
              scheduledDate &&
              new Date().toDateString() === scheduledDate.toDateString();

            return (
              <div
                key={job.id}
                className="p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-slate-50 transition space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold text-indigo-600">
                        #{job.booking_number}
                      </span>
                      {isToday && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 animate-pulse">
                          Today's Dispatch
                        </span>
                      )}
                    </div>
                    <p className="text-xs font-semibold text-slate-800 mt-1 flex items-center space-x-1">
                      <Clock className="w-3.5 h-3.5 text-slate-400 inline" />
                      <span>
                        {scheduledDate
                          ? scheduledDate.toLocaleString(undefined, {
                              weekday: 'short',
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })
                          : 'Immediate'}
                      </span>
                    </p>
                  </div>
                  <span className="text-xs font-bold text-slate-900 bg-white px-2.5 py-1 rounded-lg border border-slate-200">
                    ₹{parseFloat(job.total_amount || 0).toFixed(2)}
                  </span>
                </div>

                {/* Job Preparation Info */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-slate-200/60 text-[11px] text-slate-600">
                  <div className="flex items-center space-x-1.5">
                    <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate">{job.address || 'Address on file'}</span>
                  </div>
                  <div className="flex items-center space-x-1.5">
                    <Wrench className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                    <span>Prep: Inspect toolkit & diagnostic OBD scanner</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
