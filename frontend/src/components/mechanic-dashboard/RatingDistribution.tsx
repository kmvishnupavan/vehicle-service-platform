import React from 'react';
import { Star, MessageSquare } from 'lucide-react';

interface RatingDistributionProps {
  distribution: { [key: string]: number };
  reviewCount: number;
  averageRating: number;
  isLoading?: boolean;
}

export const RatingDistribution: React.FC<RatingDistributionProps> = ({
  distribution,
  reviewCount,
  averageRating,
  isLoading,
}) => {
  if (isLoading) {
    return (
      <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm animate-pulse space-y-4">
        <div className="w-32 h-6 bg-slate-200 rounded" />
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-4 bg-slate-200 rounded" />
          ))}
        </div>
      </div>
    );
  }

  const stars = ['5', '4', '3', '2', '1'];

  return (
    <div className="bg-white rounded-2xl p-6 border border-slate-200/80 shadow-sm">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-base font-bold text-slate-900 tracking-tight">Rating Breakdown</h3>
          <p className="text-xs text-slate-500 mt-0.5">Customer feedback distribution</p>
        </div>
        <div className="text-right">
          {reviewCount > 0 ? (
            <div className="flex items-center space-x-1.5">
              <span className="text-2xl font-black text-slate-900">{averageRating.toFixed(1)}</span>
              <Star className="w-5 h-5 text-amber-400 fill-amber-400" />
            </div>
          ) : (
            <span className="text-xs font-medium text-slate-400 italic">No reviews yet</span>
          )}
          <span className="text-xs text-slate-500 block">
            {reviewCount} {reviewCount === 1 ? 'review' : 'reviews'}
          </span>
        </div>
      </div>

      {reviewCount === 0 ? (
        <div className="py-8 text-center text-slate-400 flex flex-col items-center justify-center space-y-2">
          <MessageSquare className="w-8 h-8 text-slate-300" />
          <p className="text-sm font-medium">No reviews yet</p>
          <p className="text-xs text-slate-400 max-w-xs">
            Ratings and reviews will appear here once customers review completed services.
          </p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {stars.map((starKey) => {
            const count = distribution[starKey] || 0;
            const percentage = reviewCount > 0 ? Math.round((count / reviewCount) * 100) : 0;

            return (
              <div key={starKey} className="flex items-center space-x-3 text-xs">
                <div className="flex items-center w-10 text-slate-600 font-semibold space-x-1">
                  <span>{starKey}</span>
                  <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                </div>
                <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-amber-400 rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
                <div className="w-12 text-right font-medium text-slate-500">
                  {count} <span className="text-slate-400 text-[10px]">({percentage}%)</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
