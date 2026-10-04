import React from 'react';
import { StarRating } from './StarRating';
import { ReviewListItem } from '../../types/review';
import { MessageSquareOff, ChevronLeft, ChevronRight } from 'lucide-react';

interface ReviewListProps {
  reviews: ReviewListItem[];
  totalCount: number;
  averageRating: number;
  limit: number;
  offset: number;
  onPageChange?: (newOffset: number) => void;
  isLoading?: boolean;
}

export const ReviewList: React.FC<ReviewListProps> = ({
  reviews,
  totalCount,
  averageRating,
  limit,
  offset,
  onPageChange,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="py-8 flex flex-col items-center justify-center space-y-2">
        <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-slate-500">Loading reviews...</p>
      </div>
    );
  }

  if (totalCount === 0 || reviews.length === 0) {
    return (
      <div className="bg-slate-50 border border-dashed border-slate-200 rounded-2xl p-8 text-center text-slate-500 space-y-2">
        <MessageSquareOff className="w-8 h-8 text-slate-400 mx-auto" />
        <h4 className="font-semibold text-sm text-slate-700">No reviews yet</h4>
        <p className="text-xs text-slate-400 max-w-xs mx-auto">
          This specialist has not received any customer reviews yet. Be the first to review after your service!
        </p>
      </div>
    );
  }

  const hasNextPage = offset + limit < totalCount;
  const hasPrevPage = offset > 0;

  return (
    <div className="space-y-4">
      {/* Header Metric */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex items-center justify-between">
        <div>
          <span className="text-xs text-slate-500 font-medium">Customer Rating</span>
          <div className="flex items-center space-x-2.5 mt-0.5">
            <span className="text-2xl font-black text-slate-900">{averageRating.toFixed(1)}</span>
            <StarRating value={Math.round(averageRating)} readOnly size="sm" />
          </div>
        </div>
        <div className="text-right">
          <span className="text-xs text-slate-500 font-medium">Total Reviews</span>
          <p className="text-lg font-bold text-slate-800 mt-0.5">
            {totalCount} {totalCount === 1 ? 'review' : 'reviews'}
          </p>
        </div>
      </div>

      {/* Review Cards */}
      <div className="divide-y divide-slate-100 bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-xs">
        {reviews.map((item) => (
          <div key={item.id} className="p-5 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <div className="w-7 h-7 rounded-full bg-slate-100 text-slate-700 flex items-center justify-center font-bold text-xs">
                  {item.customer_name ? item.customer_name[0].toUpperCase() : 'C'}
                </div>
                <span className="text-xs font-semibold text-slate-800">{item.customer_name}</span>
              </div>
              <span className="text-[11px] text-slate-400">
                {new Date(item.created_at).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </span>
            </div>

            <div className="pt-0.5">
              <StarRating value={item.rating} readOnly size="sm" />
            </div>

            {item.comment && (
              <p className="text-xs text-slate-600 leading-relaxed pt-1">
                "{item.comment}"
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Pagination Controls */}
      {totalCount > limit && onPageChange && (
        <div className="flex items-center justify-between text-xs pt-2 px-1">
          <button
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={!hasPrevPage}
            className="inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            <ChevronLeft className="w-3.5 h-3.5 mr-1" />
            Previous
          </button>
          <span className="text-slate-500 text-[11px]">
            Showing {offset + 1}–{Math.min(offset + limit, totalCount)} of {totalCount}
          </span>
          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={!hasNextPage}
            className="inline-flex items-center px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            Next
            <ChevronRight className="w-3.5 h-3.5 ml-1" />
          </button>
        </div>
      )}
    </div>
  );
};
