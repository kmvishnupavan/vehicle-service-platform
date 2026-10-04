import React, { useState, useEffect } from 'react';
import {
  Calendar,
  Clock,
  X,
  AlertCircle,
  CheckCircle2,
  CalendarCheck,
  Ban,
} from 'lucide-react';
import {
  useScheduledBooking,
  useScheduleBooking,
  useCancelScheduledBooking,
} from '../../hooks/useOperationalAutomation';

interface ScheduleBookingModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookingId: string;
  bookingNumber: string;
  canCancel?: boolean;
}

const TIME_SLOTS = [
  { label: 'Morning Slot (09:00 - 11:00)', startHour: 9, endHour: 11 },
  { label: 'Midday Slot (11:00 - 13:00)', startHour: 11, endHour: 13 },
  { label: 'Afternoon Slot (14:00 - 16:00)', startHour: 14, endHour: 16 },
  { label: 'Evening Slot (16:00 - 18:00)', startHour: 16, endHour: 18 },
];

export const ScheduleBookingModal: React.FC<ScheduleBookingModalProps> = ({
  isOpen,
  onClose,
  bookingId,
  bookingNumber,
  canCancel = true,
}) => {
  const { data: schedule, isLoading: isScheduleLoading, refetch } = useScheduledBooking(bookingId);
  const { mutateAsync: scheduleBooking, isPending: isScheduling } = useScheduleBooking();
  const { mutateAsync: cancelSchedule, isPending: isCancelling } = useCancelScheduledBooking();

  // Default to tomorrow's date
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  const minDate = new Date().toISOString().split('T')[0];
  const maxDate = new Date(Date.now() + 14 * 86400000).toISOString().split('T')[0];

  const [selectedDate, setSelectedDate] = useState(tomorrow.toISOString().split('T')[0]);
  const [selectedSlotIndex, setSelectedSlotIndex] = useState(0);
  const [cancelReason, setCancelReason] = useState('');
  const [showCancelPrompt, setShowCancelPrompt] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Live countdown state
  const [countdown, setCountdown] = useState<string>('');

  useEffect(() => {
    if (!schedule?.scheduled_start_at) return;

    const updateCountdown = () => {
      const now = new Date().getTime();
      const target = new Date(schedule.scheduled_start_at).getTime();
      const diff = target - now;

      if (diff <= 0) {
        setCountdown('Service window is starting now or has passed');
      } else {
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
        const minutes = Math.floor((diff / 1000 / 60) % 60);
        const seconds = Math.floor((diff / 1000) % 60);
        if (days > 0) {
          setCountdown(`${days}d ${hours}h ${minutes}m left`);
        } else {
          setCountdown(`${hours}h ${minutes}m ${seconds}s left`);
        }
      }
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [schedule]);

  if (!isOpen) return null;

  const handleScheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedbackMsg(null);
    try {
      const slot = TIME_SLOTS[selectedSlotIndex];
      const start = new Date(`${selectedDate}T00:00:00`);
      start.setHours(slot.startHour, 0, 0, 0);

      const end = new Date(`${selectedDate}T00:00:00`);
      end.setHours(slot.endHour, 0, 0, 0);

      await scheduleBooking({
        bookingId,
        data: {
          scheduled_start_at: start.toISOString(),
          scheduled_end_at: end.toISOString(),
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
          dispatch_window_minutes: 30,
        },
      });

      setFeedbackMsg({ type: 'success', text: 'Appointment scheduled successfully!' });
      refetch();
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.message || 'Failed to schedule appointment.' });
    }
  };

  const handleCancelSubmit = async () => {
    setFeedbackMsg(null);
    try {
      await cancelSchedule({
        bookingId,
        reason: cancelReason || 'Customer requested schedule cancellation',
      });
      setFeedbackMsg({ type: 'success', text: 'Scheduled booking cancelled.' });
      setShowCancelPrompt(false);
      refetch();
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err?.message || 'Failed to cancel schedule.' });
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl max-w-lg w-full shadow-2xl border border-slate-100 overflow-hidden transform transition-all">
        {/* Header */}
        <div className="bg-gradient-to-r from-emerald-600 to-teal-700 px-6 py-5 text-white flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-white/10 flex items-center justify-center">
              <Calendar className="w-5 h-5 text-emerald-100" />
            </div>
            <div>
              <h3 className="font-bold text-lg leading-tight">Schedule Doorstep Service</h3>
              <p className="text-xs text-emerald-100">Booking #{bookingNumber}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center transition"
          >
            <X className="w-4 h-4 text-white" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6">
          {feedbackMsg && (
            <div
              className={`p-3.5 rounded-2xl flex items-start space-x-2.5 text-xs font-semibold ${
                feedbackMsg.type === 'success'
                  ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                  : 'bg-rose-50 text-rose-800 border border-rose-200'
              }`}
            >
              {feedbackMsg.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              )}
              <span>{feedbackMsg.text}</span>
            </div>
          )}

          {/* Active Schedule Display */}
          {schedule && schedule.status === 'scheduled' ? (
            <div className="bg-emerald-50/70 border border-emerald-200/80 rounded-2xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                  <CalendarCheck className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                  Confirmed Schedule
                </span>
                <span className="text-xs font-semibold text-emerald-700">
                  {schedule.timezone}
                </span>
              </div>

              <div className="space-y-1.5 text-slate-800">
                <p className="text-sm font-bold">
                  {new Date(schedule.scheduled_start_at).toLocaleDateString(undefined, {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
                <p className="text-xs text-slate-600">
                  Time Window:{' '}
                  {new Date(schedule.scheduled_start_at).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}{' '}
                  -{' '}
                  {new Date(schedule.scheduled_end_at).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>

              {/* Countdown Banner */}
              <div className="bg-white border border-emerald-200 rounded-xl p-3 flex items-center space-x-2 text-xs">
                <Clock className="w-4 h-4 text-emerald-600 animate-pulse shrink-0" />
                <span className="font-semibold text-emerald-900">
                  Countdown: <span className="font-mono text-emerald-700">{countdown}</span>
                </span>
              </div>

              {canCancel && !showCancelPrompt && (
                <div className="pt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={() => setShowCancelPrompt(true)}
                    className="inline-flex items-center text-xs font-semibold text-rose-600 hover:text-rose-700 transition"
                  >
                    <Ban className="w-3.5 h-3.5 mr-1" />
                    Cancel Appointment
                  </button>
                </div>
              )}

              {showCancelPrompt && (
                <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl space-y-2.5">
                  <p className="text-xs font-bold text-rose-900">
                    Are you sure you want to cancel this scheduled appointment?
                  </p>
                  <input
                    type="text"
                    value={cancelReason}
                    onChange={(e) => setCancelReason(e.target.value)}
                    placeholder="Reason for cancellation (optional)"
                    className="w-full text-xs px-3 py-2 bg-white border border-rose-200 rounded-lg focus:outline-hidden focus:ring-1 focus:ring-rose-500"
                  />
                  <div className="flex justify-end space-x-2">
                    <button
                      type="button"
                      onClick={() => setShowCancelPrompt(false)}
                      className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-800 font-semibold"
                    >
                      Keep Appointment
                    </button>
                    <button
                      type="button"
                      onClick={handleCancelSubmit}
                      disabled={isCancelling}
                      className="px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-semibold hover:bg-rose-700 transition disabled:opacity-50"
                    >
                      {isCancelling ? 'Cancelling...' : 'Confirm Cancellation'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Scheduling Form */
            <form onSubmit={handleScheduleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-700 block">
                  Select Service Date
                </label>
                <input
                  type="date"
                  min={minDate}
                  max={maxDate}
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  required
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-emerald-500 font-medium"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-700 block">
                  Select Preferred Arrival Window
                </label>
                <div className="grid grid-cols-1 gap-2">
                  {TIME_SLOTS.map((slot, idx) => (
                    <label
                      key={idx}
                      className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer transition ${
                        selectedSlotIndex === idx
                          ? 'border-emerald-600 bg-emerald-50/60 text-emerald-900 font-semibold'
                          : 'border-slate-200 hover:border-slate-300 text-slate-700 text-xs'
                      }`}
                    >
                      <span className="text-xs">{slot.label}</span>
                      <input
                        type="radio"
                        name="timeSlot"
                        checked={selectedSlotIndex === idx}
                        onChange={() => setSelectedSlotIndex(idx)}
                        className="text-emerald-600 focus:ring-emerald-500"
                      />
                    </label>
                  ))}
                </div>
              </div>

              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200/80 text-[11px] text-slate-500 space-y-1">
                <p className="font-semibold text-slate-700">Dispatch Window Guarantee:</p>
                <p>
                  Our automated matching engine initiates mechanic dispatch 30 minutes prior to your window to ensure timely arrival.
                </p>
              </div>

              <div className="pt-2 flex items-center justify-end space-x-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isScheduling || isScheduleLoading}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold shadow-xs transition disabled:opacity-50 flex items-center space-x-1.5"
                >
                  {isScheduling ? (
                    <span>Scheduling...</span>
                  ) : (
                    <>
                      <CalendarCheck className="w-3.5 h-3.5 mr-1" />
                      <span>Confirm Schedule</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
