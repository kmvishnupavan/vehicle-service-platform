import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Navigation,
  Car,
  Clock,
  ArrowRight,
  AlertCircle,
  CheckCircle,
  Star,
  Calendar,
} from 'lucide-react';
import { useMyBookings } from '../hooks/useBookings';
import { BookingStatus } from '../types/booking';
import { ScheduleBookingModal } from '../components/booking/ScheduleBookingModal';

export const CustomerDashboardPage: React.FC = () => {
  const { data: bookings, isLoading, error, refetch } = useMyBookings();
  const [schedulingBooking, setSchedulingBooking] = useState<{ id: string; number: string } | null>(null);

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="flex flex-col items-center justify-center min-h-[400px] space-y-4">
          <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm font-medium text-slate-600">Loading your vehicle bookings...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center max-w-lg mx-auto">
          <AlertCircle className="w-8 h-8 text-red-600 mx-auto mb-2" />
          <h3 className="font-semibold text-slate-900">Failed to load bookings</h3>
          <p className="text-xs text-red-700 mt-1">{(error as any)?.message || 'Network error'}</p>
          <button
            onClick={() => refetch()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg text-xs font-semibold hover:bg-red-700 transition"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const allBookings = bookings || [];

  const isLiveTrackingStatus = (status: BookingStatus) =>
    ['mechanic_en_route', 'mechanic_arrived', 'service_in_progress', 'additional_work'].includes(
      status
    );

  const activeBookings = allBookings.filter(
    (b) =>
      ![
        'service_completed',
        'paid',
        'cancelled',
        'disputed',
      ].includes(b.booking_status)
  );

  const pastBookings = allBookings.filter((b) =>
    ['service_completed', 'paid', 'cancelled', 'disputed'].includes(b.booking_status)
  );

  const getStatusBadge = (status: BookingStatus) => {
    switch (status) {
      case 'mechanic_en_route':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
            <span className="w-2 h-2 rounded-full bg-emerald-600 mr-1.5 animate-ping" />
            Mechanic En Route
          </span>
        );
      case 'mechanic_arrived':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
            Mechanic Arrived
          </span>
        );
      case 'service_in_progress':
      case 'additional_work':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800">
            Service in Progress
          </span>
        );
      case 'mechanic_assigned':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">
            Mechanic Assigned
          </span>
        );
      case 'service_completed':
      case 'paid':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-800">
            <CheckCircle className="w-3.5 h-3.5 mr-1 text-emerald-600" />
            Completed
          </span>
        );
      case 'cancelled':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800">
            Cancelled
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 capitalize">
            {status.replace(/_/g, ' ')}
          </span>
        );
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Customer Dashboard</h1>
          <p className="text-xs text-slate-500 mt-1">
            Monitor service appointments, dispatch status, and live mechanic arrival.
          </p>
        </div>
      </div>

      {/* Active Service Bookings */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900 flex items-center space-x-2">
            <span>Active & Upcoming Bookings</span>
            <span className="bg-emerald-100 text-emerald-800 text-xs px-2 py-0.5 rounded-full font-semibold">
              {activeBookings.length}
            </span>
          </h2>
        </div>

        {activeBookings.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center text-slate-500">
            <Car className="w-10 h-10 text-slate-400 mx-auto mb-2" />
            <p className="text-sm font-semibold text-slate-700">No active bookings</p>
            <p className="text-xs text-slate-500 mt-1">
              All your booked services are complete or you haven't scheduled one yet.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {activeBookings.map((booking) => {
              const canTrack = isLiveTrackingStatus(booking.booking_status);
              const items = booking.items || booking.booking_items || [];
              const primaryService = items[0]?.services?.name || 'Vehicle Service';

              return (
                <div
                  key={booking.id}
                  className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md transition flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <span className="text-[11px] font-bold text-emerald-600 uppercase tracking-wider">
                          #{booking.booking_number}
                        </span>
                        <h3 className="font-bold text-slate-900 text-base mt-0.5">
                          {primaryService}
                        </h3>
                      </div>
                      <div>{getStatusBadge(booking.booking_status)}</div>
                    </div>

                    <div className="text-xs text-slate-600 space-y-1.5 pt-1">
                      <div className="flex items-center space-x-2">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span>
                          {booking.scheduled_at
                            ? new Date(booking.scheduled_at).toLocaleDateString(undefined, {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })
                            : 'Immediate Dispatch'}
                        </span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="font-semibold text-slate-800">
                          ₹{parseFloat(booking.total_amount).toFixed(2)}
                        </span>
                        <span className="text-slate-400">•</span>
                        <span className="capitalize text-slate-500">
                          {booking.payment_status}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mt-5 pt-4 border-t border-slate-100 flex items-center justify-between gap-2">
                    <div className="flex items-center space-x-2">
                      <Link
                        to={`/bookings/${booking.id}`}
                        className="text-xs font-semibold text-slate-700 hover:text-slate-900 transition flex items-center"
                      >
                        Details
                        <ArrowRight className="w-3.5 h-3.5 ml-1" />
                      </Link>

                      {['pending', 'searching_mechanic'].includes(booking.booking_status) && (
                        <button
                          type="button"
                          onClick={() =>
                            setSchedulingBooking({
                              id: booking.id,
                              number: booking.booking_number,
                            })
                          }
                          className="inline-flex items-center text-xs font-semibold text-emerald-700 hover:text-emerald-800 transition px-2 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 border border-emerald-200"
                        >
                          <Calendar className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                          {booking.scheduled_at ? 'Manage Schedule' : 'Schedule'}
                        </button>
                      )}
                    </div>

                    {canTrack ? (
                      <Link
                        to={`/bookings/${booking.id}/tracking`}
                        className="inline-flex items-center px-3.5 py-1.5 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 shadow-sm transition"
                      >
                        <Navigation className="w-3.5 h-3.5 mr-1.5 animate-pulse" />
                        Track Mechanic
                      </Link>
                    ) : (
                      <span className="text-[11px] text-slate-400 italic">
                        Tracking starts en-route
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Schedule Booking Modal */}
        {schedulingBooking && (
          <ScheduleBookingModal
            isOpen={!!schedulingBooking}
            onClose={() => setSchedulingBooking(null)}
            bookingId={schedulingBooking.id}
            bookingNumber={schedulingBooking.number}
            canCancel={true}
          />
        )}
      </section>

      {/* Past Bookings */}
      {pastBookings.length > 0 && (
        <section className="space-y-4 pt-4">
          <h2 className="text-base font-bold text-slate-900">Past Bookings</h2>
          <div className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden shadow-sm">
            {pastBookings.map((b) => (
              <div key={b.id} className="p-4 sm:p-5 flex items-center justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-sm text-slate-900">#{b.booking_number}</span>
                    {getStatusBadge(b.booking_status)}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    Completed on {new Date(b.updated_at).toLocaleDateString()} • ₹
                    {parseFloat(b.total_amount).toFixed(2)}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  {['service_completed', 'paid'].includes(b.booking_status) && b.assigned_mechanic && (
                    <Link
                      to={`/bookings/${b.id}/review`}
                      className="inline-flex items-center px-3 py-1.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 text-xs font-semibold transition"
                    >
                      <Star className="w-3 h-3 mr-1 text-amber-500 fill-amber-500" />
                      Leave Review
                    </Link>
                  )}
                  <Link
                    to={`/bookings/${b.id}`}
                    className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                  >
                    View Receipt
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};
