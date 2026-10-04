import React from 'react';
import { Star, MessageSquare, User } from 'lucide-react';
import { RecentReviewsList, RecentReviewItem } from '../../types/mechanic-dashboard';

interface RecentReviewsProps {
  reviews?: RecentReviewsList;
  isLoading: boolean;
}

export const RecentReviews: React.FC<RecentReviewsProps> = ({ reviews, isLoading }) => {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm animate-pulse space-y-4">
        <div className="w-32 h-6 bg-slate-200 rounded" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-slate-100 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const items = reviews?.items || [];

  return (
    <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <MessageSquare className="w-5 h-5 text-emerald-600" />
            <span>Recent Customer Reviews</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Verified ratings and feedback from completed jobs
          </p>
        </div>
        <span className="text-xs font-semibold text-slate-500">
          {items.length} {items.length === 1 ? 'review' : 'reviews'}
        </span>
      </div>

      {items.length === 0 ? (
        <div className="py-10 text-center text-slate-400 space-y-2">
          <MessageSquare className="w-8 h-8 text-slate-300 mx-auto" />
          <p className="text-sm font-medium">No customer reviews yet</p>
          <p className="text-xs text-slate-400">
            Ratings and comments will appear here as customers complete feedback.
          </p>
        </div>
      ) : (
        <div className="space-y-3.5">
          {items.map((review: RecentReviewItem) => (
            <div
              key={review.id}
              className="p-3.5 rounded-xl border border-slate-100 bg-slate-50/50 space-y-2 hover:bg-slate-50 transition"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <div className="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center text-slate-600">
                    <User className="w-3.5 h-3.5" />
                  </div>
                  <span className="text-xs font-bold text-slate-800">
                    {review.customer_name}
                  </span>
                </div>

                <div className="flex items-center space-x-1">
                  {[1, 2, 3, 4, 5].map((s) => (
                    <Star
                      key={s}
                      className={`w-3.5 h-3.5 ${
                        s <= review.rating
                          ? 'text-amber-400 fill-amber-400'
                          : 'text-slate-200'
                      }`}
                    />
                  ))}
                  <span className="text-xs font-bold text-slate-700 ml-1">
                    {review.rating}.0
                  </span>
                </div>
              </div>

              {review.review_text && (
                <p className="text-xs text-slate-600 italic">
                  "{review.review_text}"
                </p>
              )}

              <div className="text-[10px] text-slate-400 text-right">
                {new Date(review.created_at).toLocaleDateString(undefined, {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
