import React, { useState } from 'react';
import { z } from 'zod';
import { StarRating } from './StarRating';
import { AlertCircle, CheckCircle2, Loader2, Sparkles } from 'lucide-react';
import { ReviewSubmissionPayload } from '../../types/review';

const reviewSchema = z.object({
  rating: z
    .number({ required_error: 'Please select a star rating.' })
    .int('Rating must be an integer.')
    .min(1, 'Please select at least 1 star.')
    .max(5, 'Maximum rating is 5 stars.'),
  comment: z
    .string()
    .max(1000, 'Review comment cannot exceed 1000 characters.')
    .optional()
    .transform((val) => (val && val.trim() ? val.trim() : null)),
});

interface ReviewFormProps {
  mechanicName?: string;
  bookingId: string;
  onSubmit: (payload: ReviewSubmissionPayload) => Promise<void>;
  isSubmitting?: boolean;
  onSuccess?: () => void;
  className?: string;
}

export const ReviewForm: React.FC<ReviewFormProps> = ({
  mechanicName = 'Your Assigned Specialist',
  bookingId,
  onSubmit,
  isSubmitting = false,
  onSuccess,
  className = '',
}) => {
  const [rating, setRating] = useState<number>(0);
  const [comment, setComment] = useState<string>('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isDone, setIsDone] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setValidationError(null);
    setServerError(null);

    const parseResult = reviewSchema.safeParse({ rating, comment });
    if (!parseResult.success) {
      const issue = parseResult.error.issues[0];
      setValidationError(issue.message);
      return;
    }

    try {
      await onSubmit({
        rating: parseResult.data.rating,
        comment: parseResult.data.comment,
      });
      setIsDone(true);
      if (onSuccess) {
        onSuccess();
      }
    } catch (err: any) {
      setServerError(err.message || 'Failed to submit review. Please try again.');
    }
  };

  if (isDone) {
    return (
      <div className={`bg-white border border-emerald-200 rounded-2xl p-8 text-center shadow-sm ${className}`}>
        <div className="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-3">
          <CheckCircle2 className="w-6 h-6 text-emerald-600" />
        </div>
        <h3 className="text-lg font-bold text-slate-900">Review Submitted!</h3>
        <p className="text-xs text-slate-600 mt-1 max-w-sm mx-auto">
          Thank you for rating your service. Your feedback directly helps {mechanicName} and our community.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={`bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 shadow-sm space-y-6 ${className}`}
      data-booking-id={bookingId}
    >
      <div className="border-b border-slate-100 pb-4">
        <div className="flex items-center space-x-2 text-emerald-600 font-semibold text-xs uppercase tracking-wider">
          <Sparkles className="w-4 h-4" />
          <span>Service Feedback</span>
        </div>
        <h2 className="text-xl font-bold text-slate-900 mt-1">Rate your service</h2>
        <p className="text-xs text-slate-500 mt-0.5">
          Specialist: <span className="font-semibold text-slate-800">{mechanicName}</span>
        </p>
      </div>

      {validationError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl p-3.5 flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{validationError}</span>
        </div>
      )}

      {serverError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl p-3.5 flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{serverError}</span>
        </div>
      )}

      <div className="text-center py-2 space-y-2">
        <label htmlFor="booking-rating-picker" className="block text-xs font-semibold text-slate-700">
          How would you rate your overall experience?
        </label>
        <StarRating
          id="booking-rating-picker"
          value={rating}
          onChange={(val) => {
            setRating(val);
            if (validationError) setValidationError(null);
          }}
          size="lg"
        />
        <p className="text-[11px] text-slate-400">
          {rating === 0
            ? 'Tap a star to rate (1 = Poor, 5 = Excellent)'
            : rating === 5
            ? '5 stars — Outstanding!'
            : rating === 4
            ? '4 stars — Great service'
            : rating === 3
            ? '3 stars — Average'
            : rating === 2
            ? '2 stars — Needs improvement'
            : '1 star — Poor experience'}
        </p>
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between items-center">
          <label htmlFor="review-comment" className="text-xs font-semibold text-slate-700">
            Written Review <span className="text-slate-400 font-normal">(Optional)</span>
          </label>
          <span className="text-[11px] text-slate-400">{comment.length} / 1000</span>
        </div>
        <textarea
          id="review-comment"
          rows={4}
          value={comment}
          maxLength={1000}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Share your experience with the mechanic, vehicle repairs, or timeliness..."
          className="w-full text-xs rounded-xl border border-slate-200 p-3.5 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-200 outline-none transition text-slate-800 placeholder-slate-400 resize-none"
        />
      </div>

      <button
        type="submit"
        disabled={isSubmitting || rating === 0}
        className="w-full py-3 px-4 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300 disabled:cursor-not-allowed transition flex items-center justify-center space-x-2 shadow-sm"
      >
        {isSubmitting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            <span>Submitting Review...</span>
          </>
        ) : (
          <span>Submit Review</span>
        )}
      </button>
    </form>
  );
};
