import React, { useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Navigation,
  MapPin,
  Car,
  Receipt,
  AlertCircle,
  MessageSquare,
  Star,
  CreditCard,
} from 'lucide-react';
import { useBooking } from '../hooks/useBookings';
import { useBookingReview } from '../hooks/useReview';
import { BookingStatusTimeline } from '../components/booking/BookingStatusTimeline';
import { MechanicInfoCard } from '../components/booking/MechanicInfoCard';
import { StarRating } from '../components/review/StarRating';
import { PaymentModal } from '../components/booking/PaymentModal';

export const BookingDetailsPage: React.FC = () => {
  const { bookingId } = useParams<{ bookingId: string }>();
  const navigate = useNavigate();
  const { data: booking, isLoading, error } = useBooking(bookingId);
  const { data: review } = useBookingReview(bookingId);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12 flex flex-col items-center justify-center space-y-4">
        <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-600">Loading booking details...</p>
      </div>
    );
  }

  if (error || !booking) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center max-w-md mx-auto">
          <AlertCircle className="w-8 h-8 text-red-600 mx-auto mb-2" />
          <h3 className="font-semibold text-slate-900">Booking Not Found</h3>
          <p className="text-xs text-red-700 mt-1">
            {(error as any)?.message || 'We could not locate this booking.'}
          </p>
          <Link
            to="/dashboard"
            className="mt-4 inline-block px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  const items = booking.items || booking.booking_items || [];
  const canTrack = [
    'mechanic_en_route',
    'mechanic_arrived',
    'service_in_progress',
    'additional_work',
  ].includes(booking.booking_status);

  const isEligibleForReview =
    ['service_completed', 'payment_pending', 'paid'].includes(booking.booking_status) &&
    Boolean(booking.assigned_mechanic);

  const isEligibleForPayment =
    ['service_completed', 'payment_pending'].includes(booking.booking_status) &&
    booking.payment_status !== 'paid';

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Top Bar */}
      <div className="flex items-center justify-between">
        <Link
          to="/dashboard"
          className="inline-flex items-center text-xs font-semibold text-slate-600 hover:text-slate-900 transition"
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" />
          Back to Dashboard
        </Link>

        <div className="flex items-center space-x-2">
          {booking.assigned_mechanic && (
            <Link
              to={`/bookings/${booking.id}/chat`}
              className="inline-flex items-center px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 shadow-xs transition"
            >
              <MessageSquare className="w-3.5 h-3.5 mr-1.5 text-emerald-600" />
              Chat
            </Link>
          )}

          {isEligibleForPayment && (
            <button
              type="button"
              onClick={() => setIsPaymentModalOpen(true)}
              className="inline-flex items-center px-4 py-2 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 shadow-sm transition"
            >
              <CreditCard className="w-4 h-4 mr-1.5" />
              Pay Now (₹{parseFloat(booking.total_amount).toFixed(2)})
            </button>
          )}

          {isEligibleForReview && !review && (
            <Link
              to={`/bookings/${booking.id}/review`}
              className="inline-flex items-center px-3.5 py-2 rounded-xl text-xs font-bold text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-300 shadow-xs transition"
            >
              <Star className="w-3.5 h-3.5 mr-1.5 text-amber-500 fill-amber-500" />
              Rate Service
            </Link>
          )}

          {canTrack && (
            <Link
              to={`/bookings/${booking.id}/tracking`}
              className="inline-flex items-center px-4 py-2 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 shadow-sm transition"
            >
              <Navigation className="w-4 h-4 mr-1.5 animate-pulse" />
              Live Map Tracking
            </Link>
          )}
        </div>
      </div>

      {/* Main Header Card */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">
              Booking #{booking.booking_number}
            </span>
            <h1 className="text-xl font-bold text-slate-900 mt-0.5">Service Details</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Created on {new Date(booking.created_at).toLocaleDateString()} at{' '}
              {new Date(booking.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
          <div className="text-left sm:text-right">
            <span className="text-xs text-slate-500 block">Total Amount</span>
            <span className="text-2xl font-black text-slate-900">
              ₹{parseFloat(booking.total_amount).toFixed(2)}
            </span>
          </div>
        </div>

        {/* State Machine Timeline */}
        <div className="pt-2">
          <BookingStatusTimeline currentStatus={booking.booking_status} />
        </div>
      </div>

      {/* Mechanic Section */}
      <section className="space-y-2">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
          Assigned Service Specialist
        </h2>
        <MechanicInfoCard
          mechanic={booking.assigned_mechanic}
          bookingStatus={booking.booking_status}
          bookingId={booking.id}
          onOpenChat={() => navigate(`/bookings/${booking.id}/chat`)}
        />
      </section>

      {/* Review Section */}
      {review ? (
        <section className="bg-white border border-emerald-200 rounded-2xl p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
            <div className="flex items-center space-x-2">
              <Star className="w-4 h-4 text-amber-500 fill-amber-500" />
              <h2 className="text-sm font-bold text-slate-900">Your Review</h2>
            </div>
            <span className="text-[11px] text-slate-400">
              {new Date(review.created_at).toLocaleDateString()}
            </span>
          </div>
          <div className="space-y-2">
            <div className="flex items-center space-x-2">
              <StarRating value={review.rating} readOnly size="sm" />
              <span className="text-xs font-bold text-slate-800">{review.rating} / 5 Stars</span>
            </div>
            {review.comment && (
              <p className="text-xs text-slate-600 bg-slate-50 border border-slate-100 rounded-xl p-3 leading-relaxed italic">
                "{review.comment}"
              </p>
            )}
          </div>
        </section>
      ) : isEligibleForReview ? (
        <section className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200/80 rounded-2xl p-5 shadow-xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center space-x-1.5 text-amber-800 font-semibold text-xs uppercase tracking-wider">
              <Star className="w-4 h-4 text-amber-500 fill-amber-500" />
              <span>Service Completed</span>
            </div>
            <h3 className="text-base font-bold text-slate-900">How was your service experience?</h3>
            <p className="text-xs text-slate-600">
              Rate {booking.assigned_mechanic?.business_name || booking.assigned_mechanic?.full_name || 'your specialist'} and share your feedback.
            </p>
          </div>
          <Link
            to={`/bookings/${booking.id}/review`}
            className="inline-flex items-center justify-center px-4 py-2.5 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 shadow-sm transition shrink-0"
          >
            <Star className="w-3.5 h-3.5 mr-1.5 text-amber-400 fill-amber-400" />
            Rate Your Service
          </Link>
        </section>
      ) : null}

      {/* Grid: Services & Address */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Booked Items */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
          <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <Receipt className="w-4 h-4 text-emerald-600" />
            <span>Service Line Items</span>
          </h2>
          <div className="divide-y divide-slate-100">
            {items.map((item) => (
              <div key={item.id} className="py-2.5 flex justify-between items-center text-xs">
                <div>
                  <p className="font-semibold text-slate-800">
                    {item.services?.name || 'Standard Service'}
                  </p>
                  {item.services?.description && (
                    <p className="text-slate-500 text-[11px] line-clamp-1">
                      {item.services.description}
                    </p>
                  )}
                </div>
                <span className="font-bold text-slate-900 ml-4">
                  ₹{parseFloat(item.unit_price).toFixed(2)}
                </span>
              </div>
            ))}
          </div>

          <div className="border-t border-slate-100 pt-3 text-xs space-y-1.5 text-slate-600">
            <div className="flex justify-between">
              <span>Subtotal</span>
              <span>₹{parseFloat(booking.subtotal).toFixed(2)}</span>
            </div>
            {parseFloat(booking.additional_charges) > 0 && (
              <div className="flex justify-between text-amber-700">
                <span>Additional Approved Work</span>
                <span>+₹{parseFloat(booking.additional_charges).toFixed(2)}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span>GST (18%)</span>
              <span>₹{parseFloat(booking.tax_amount).toFixed(2)}</span>
            </div>
            <div className="flex justify-between font-bold text-slate-900 text-sm pt-1 border-t border-slate-100">
              <span>Grand Total</span>
              <span>₹{parseFloat(booking.total_amount).toFixed(2)}</span>
            </div>
          </div>
        </div>

        {/* Location & Vehicle */}
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-2">
            <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <MapPin className="w-4 h-4 text-emerald-600" />
              <span>Service Location</span>
            </h2>
            <p className="text-xs text-slate-700 font-medium leading-relaxed">
              {booking.address?.street_address || 'Customer Specified Location'}
              <br />
              {booking.address?.city && `${booking.address.city}, `}
              {booking.address?.state && `${booking.address.state} `}
              {booking.address?.postal_code}
            </p>
          </div>

          {booking.vehicle && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-2">
              <h2 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
                <Car className="w-4 h-4 text-emerald-600" />
                <span>Vehicle Details</span>
              </h2>
              <div className="text-xs text-slate-700">
                <span className="font-bold text-slate-900 block text-sm">
                  {booking.vehicle.license_plate}
                </span>
                <span className="text-slate-500">
                  {booking.vehicle.vehicle_models?.brands?.name}{' '}
                  {booking.vehicle.vehicle_models?.name}{' '}
                  {booking.vehicle.year && `(${booking.vehicle.year})`}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      <PaymentModal
        isOpen={isPaymentModalOpen}
        onClose={() => setIsPaymentModalOpen(false)}
        bookingId={booking.id}
        bookingNumber={booking.booking_number || booking.id.slice(0, 8).toUpperCase()}
        totalAmount={booking.total_amount}
      />
    </div>
  );
};
