import React from 'react';
import { Star, Award, MessageSquare, ShieldCheck, User } from 'lucide-react';
import { AssignedMechanicProfile, BookingStatus } from '../../types/booking';

interface Props {
  mechanic: AssignedMechanicProfile | null | undefined;
  bookingStatus: BookingStatus;
  bookingId: string;
  onOpenChat?: () => void;
}

export const MechanicInfoCard: React.FC<Props> = ({
  mechanic,
  bookingStatus,
  bookingId,
  onOpenChat,
}) => {
  if (!mechanic) {
    return (
      <div className="bg-slate-50 border border-dashed border-slate-300 rounded-xl p-6 text-center text-slate-500">
        <User className="w-8 h-8 mx-auto text-slate-400 mb-2" />
        <h4 className="font-semibold text-sm text-slate-700">Waiting for Mechanic Assignment</h4>
        <p className="text-xs text-slate-500 mt-1 max-w-xs mx-auto">
          We are matching your service request with a verified automotive specialist in your area.
        </p>
      </div>
    );
  }

  const rawAvg =
    typeof mechanic.average_rating === 'number'
      ? mechanic.average_rating
      : parseFloat(String(mechanic.average_rating || 0));
  const reviewCount = mechanic.review_count ?? 0;
  const hasReviews = reviewCount > 0 || rawAvg > 0;
  const rating = rawAvg.toFixed(1);

  const getStatusBadge = () => {
    switch (bookingStatus) {
      case 'mechanic_en_route':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 mr-1.5 animate-pulse" />
            En Route to You
          </span>
        );
      case 'mechanic_arrived':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            Arrived on Site
          </span>
        );
      case 'service_in_progress':
      case 'additional_work':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
            Service in Progress
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
            Assigned
          </span>
        );
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm" data-booking-id={bookingId}>
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-3.5">
          {mechanic.avatar_url ? (
            <img
              src={mechanic.avatar_url}
              alt={mechanic.full_name || 'Mechanic'}
              className="w-12 h-12 rounded-full object-cover border border-slate-200"
            />
          ) : (
            <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-base border border-emerald-200">
              {mechanic.full_name ? mechanic.full_name.charAt(0).toUpperCase() : 'M'}
            </div>
          )}

          <div>
            <div className="flex items-center space-x-1.5">
              <h3 className="font-semibold text-slate-900 text-base leading-snug">
                {mechanic.full_name || 'Assigned Mechanic'}
              </h3>
              <span title="Verified Professional">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
              </span>
            </div>

            {mechanic.business_name && (
              <p className="text-xs text-slate-500 font-medium">{mechanic.business_name}</p>
            )}

            <div className="flex items-center space-x-3 mt-1.5 text-xs text-slate-600">
              {hasReviews ? (
                <>
                  <div className="flex items-center space-x-1">
                    <Star className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
                    <span className="font-semibold text-slate-800">{rating}</span>
                    {reviewCount > 0 && (
                      <span className="text-slate-400">
                        ({reviewCount} {reviewCount === 1 ? 'review' : 'reviews'})
                      </span>
                    )}
                  </div>
                  <span>•</span>
                </>
              ) : (
                <>
                  <span className="text-slate-400 italic">No reviews yet</span>
                  <span>•</span>
                </>
              )}
              <div className="flex items-center space-x-1">
                <Award className="w-3.5 h-3.5 text-slate-400" />
                <span>{mechanic.experience_years || 3}+ yrs exp</span>
              </div>
            </div>
          </div>
        </div>

        <div>{getStatusBadge()}</div>
      </div>

      <div className="mt-4 pt-3.5 border-t border-slate-100 flex items-center justify-between">
        <span className="text-xs text-slate-500">Contact via secure in-app chat</span>
        <button
          onClick={onOpenChat}
          className="inline-flex items-center px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 shadow-sm transition"
        >
          <MessageSquare className="w-3.5 h-3.5 mr-1.5" />
          Chat with Mechanic
        </button>
      </div>
    </div>
  );
};
