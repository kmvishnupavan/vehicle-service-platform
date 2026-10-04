import React, { useState } from 'react';
import { Star } from 'lucide-react';

interface StarRatingProps {
  value: number;
  onChange?: (rating: number) => void;
  readOnly?: boolean;
  size?: 'sm' | 'md' | 'lg';
  id?: string;
}

export const StarRating: React.FC<StarRatingProps> = ({
  value,
  onChange,
  readOnly = false,
  size = 'md',
  id = 'star-rating',
}) => {
  const [hoverValue, setHoverValue] = useState<number | null>(null);

  const starSizes = {
    sm: 'w-4 h-4',
    md: 'w-7 h-7',
    lg: 'w-9 h-9',
  };

  const activeValue = hoverValue !== null ? hoverValue : value;

  const handleKeyDown = (e: React.KeyboardEvent, star: number) => {
    if (readOnly || !onChange) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onChange(star);
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      e.preventDefault();
      onChange(Math.min(5, value + 1));
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      e.preventDefault();
      onChange(Math.max(1, value - 1));
    }
  };

  return (
    <div
      id={id}
      role={readOnly ? 'img' : 'radiogroup'}
      aria-label={readOnly ? `${value} out of 5 stars` : 'Rate your service from 1 to 5 stars'}
      className="inline-flex items-center space-x-1.5 focus:outline-none"
    >
      {[1, 2, 3, 4, 5].map((star) => {
        const isFilled = star <= activeValue;

        if (readOnly) {
          return (
            <Star
              key={star}
              className={`${starSizes[size]} transition-colors duration-150 ${
                isFilled ? 'text-amber-500 fill-amber-500' : 'text-slate-200 fill-slate-100'
              }`}
              aria-hidden="true"
            />
          );
        }

        return (
          <button
            key={star}
            type="button"
            role="radio"
            aria-checked={value === star}
            aria-label={`${star} ${star === 1 ? 'star' : 'stars'}`}
            disabled={readOnly}
            onMouseEnter={() => setHoverValue(star)}
            onMouseLeave={() => setHoverValue(null)}
            onClick={() => onChange && onChange(star)}
            onKeyDown={(e) => handleKeyDown(e, star)}
            className="p-1 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 hover:scale-110 active:scale-95 transition-transform cursor-pointer"
          >
            <Star
              className={`${starSizes[size]} transition-colors duration-150 ${
                isFilled
                  ? 'text-amber-500 fill-amber-500 drop-shadow-xs'
                  : 'text-slate-300 fill-transparent hover:text-amber-400'
              }`}
            />
          </button>
        );
      })}
      {!readOnly && (
        <span className="sr-only">
          {value > 0 ? `${value} stars selected` : 'No rating selected'}
        </span>
      )}
    </div>
  );
};
