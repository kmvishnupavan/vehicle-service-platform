import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useBooking } from '../hooks/useBookings';
import { useBookingReview, useSubmitReview } from '../hooks/useReview';
import { ReviewForm } from '../components/review/ReviewForm';
import { StarRating } from '../components/review/StarRating';
import { ReviewSubmissionPayload } from '../types/review';

export const BookingReviewPage: React.FC = () => {
  const { bookingId } = useParams<{ bookingId: string }>();

  const { data: booking, isLoading: isBookingLoading, error: bookingError } = useBooking(bookingId);
  const { data: existingReview, isLoading: isReviewLoading } = useBookingReview(bookingId);
  const submitReview = useSubmitReview();

  if (isBookingLoading || isReviewLoading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 flex flex-col items-center justify-center space-y-4">
        <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-medium text-slate-600">Loading booking information...</p>
      </div>
    );
  }

  if (bookingError || !booking) {
    return (
      <div className="max-w-md mx-auto px-4 py-16 text-center space-y-4">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-8">
          <AlertCircle className="w-8 h-8 text-red-600 mx-auto mb-2" />
          <h3 className="font-semibold text-slate-900">Booking Not Found</h3>
          <p className="text-xs text-red-700 mt-1">
            {(bookingError as any)?.message || 'We could not locate this booking.'}
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

  const isEligible = ['service_completed', 'payment_pending', 'paid'].includes(booking.booking_status);
  const mechanicName =
    booking.assigned_mechanic?.business_name ||
    booking.assigned_mechanic?.full_name ||
    'Your Assigned Specialist';

  const handleReviewSubmit = async (payload: ReviewSubmissionPayload) => {
    if (!bookingId) return;
    await submitReview.mutateAsync({
      bookingId,
      payload,
    });
  };

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 space-y-6">
      {/* Navigation Top Bar */}
      <div>
        <Link
          to={`/bookings/${booking.id}`}
          className="inline-flex items-center text-xs font-semibold text-slate-600 hover:text-slate-900 transition"
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" />
          Back to Booking Details
        </Link>
      </div>

      {/* Booking Header Banner */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex items-center justify-between">
        <div>
          <span className="text-[11px] font-bold text-emerald-600 uppercase tracking-wider">
            Booking #{booking.booking_number}
          </span>
          <h1 className="text-lg font-bold text-slate-900 mt-0.5">Rate Your Service</h1>
          <p className="text-xs text-slate-500">
            Mechanic: <span className="font-semibold text-slate-700">{mechanicName}</span>
          </p>
        </div>
        <div className="text-right">
          <span className="text-xs text-slate-500 block">Total Paid</span>
          <span className="text-base font-bold text-slate-900">
            ₹{parseFloat(booking.total_amount).toFixed(2)}
          </span>
        </div>
      </div>

      {/* Existing Review Display */}
      {existingReview ? (
        <div className="bg-white border border-emerald-200 rounded-2xl p-6 sm:p-8 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center space-x-2 text-emerald-700 font-semibold text-xs uppercase tracking-wider">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Your Submitted Review</span>
            </div>
            <span className="text-[11px] text-slate-400">
              {new Date(existingReview.created_at).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
            </span>
          </div>

          <div className="space-y-3">
            <div className="flex items-center space-x-2">
              <StarRating value={existingReview.rating} readOnly size="md" />
              <span className="text-sm font-bold text-slate-800">
                {existingReview.rating} / 5 Stars
              </span>
            </div>

            {existingReview.comment ? (
              <p className="text-xs text-slate-700 bg-slate-50 border border-slate-100 rounded-xl p-4 leading-relaxed italic">
                "{existingReview.comment}"
              </p>
            ) : (
              <p className="text-xs text-slate-400 italic">No written comment provided.</p>
            )}
          </div>

          <div className="pt-2">
            <Link
              to={`/bookings/${booking.id}`}
              className="inline-block text-xs font-semibold text-emerald-600 hover:text-emerald-700"
            >
              ← Return to booking details
            </Link>
          </div>
        </div>
      ) : !isEligible ? (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-6 text-center space-y-2">
          <AlertCircle className="w-6 h-6 text-amber-600 mx-auto" />
          <h3 className="font-semibold text-sm text-slate-900">Review Not Yet Available</h3>
          <p className="text-xs text-amber-800 max-w-sm mx-auto">
            Reviews can only be submitted once your service is marked as completed by your specialist.
          </p>
          <Link
            to={`/bookings/${booking.id}`}
            className="mt-3 inline-block px-4 py-2 bg-slate-900 text-white rounded-xl text-xs font-semibold"
          >
            View Live Booking Status
          </Link>
        </div>
      ) : !booking.assigned_mechanic ? (
        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 text-center space-y-2">
          <AlertCircle className="w-6 h-6 text-slate-500 mx-auto" />
          <h3 className="font-semibold text-sm text-slate-900">No Specialist Assigned</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            This booking did not have an assigned specialist recorded to review.
          </p>
        </div>
      ) : (
        <ReviewForm
          mechanicName={mechanicName}
          bookingId={booking.id}
          onSubmit={handleReviewSubmit}
          isSubmitting={submitReview.isPending}
        />
      )}
    </div>
  );
};
