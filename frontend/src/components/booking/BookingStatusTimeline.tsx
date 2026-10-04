import React from 'react';
import { CheckCircle2, Clock, AlertTriangle, XCircle } from 'lucide-react';
import { BookingStatus } from '../../types/booking';

interface TimelineStep {
  id: string;
  label: string;
  description: string;
  statuses: BookingStatus[];
}

const STEPS: TimelineStep[] = [
  {
    id: 'created',
    label: 'Booking Created',
    description: 'Service requested & confirmed',
    statuses: ['pending', 'confirmed'],
  },
  {
    id: 'assigned',
    label: 'Mechanic Assigned',
    description: 'Mechanic accepted the job',
    statuses: ['mechanic_assigned'],
  },
  {
    id: 'en_route',
    label: 'Mechanic on the Way',
    description: 'Live GPS tracking active',
    statuses: ['mechanic_en_route'],
  },
  {
    id: 'arrived',
    label: 'Mechanic Arrived',
    description: 'At vehicle location',
    statuses: ['mechanic_arrived'],
  },
  {
    id: 'inspection',
    label: 'Inspection & Approval',
    description: 'Vehicle diagnostic check',
    statuses: ['inspection', 'awaiting_customer_approval'],
  },
  {
    id: 'service',
    label: 'Service in Progress',
    description: 'Maintenance & repairs',
    statuses: ['service_in_progress', 'additional_work'],
  },
  {
    id: 'completed',
    label: 'Service Completed',
    description: 'Work done & verified',
    statuses: ['service_completed', 'payment_pending', 'paid'],
  },
];

interface Props {
  currentStatus: BookingStatus;
}

export const BookingStatusTimeline: React.FC<Props> = ({ currentStatus }) => {
  if (currentStatus === 'cancelled') {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-center space-x-3 text-red-800">
        <XCircle className="w-6 h-6 text-red-600 flex-shrink-0" />
        <div>
          <h4 className="font-semibold text-sm">Booking Cancelled</h4>
          <p className="text-xs text-red-700">This service booking has been cancelled and is no longer active.</p>
        </div>
      </div>
    );
  }

  if (currentStatus === 'disputed') {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center space-x-3 text-amber-800">
        <AlertTriangle className="w-6 h-6 text-amber-600 flex-shrink-0" />
        <div>
          <h4 className="font-semibold text-sm">Booking Under Review / Disputed</h4>
          <p className="text-xs text-amber-700">Our customer support team is mediating this booking.</p>
        </div>
      </div>
    );
  }

  // Determine which step is currently active
  const activeStepIndex = STEPS.findIndex((s) => s.statuses.includes(currentStatus));
  const currentStep = activeStepIndex === -1 ? 0 : activeStepIndex;

  return (
    <div className="py-2">
      <div className="relative">
        <div className="absolute top-4 left-4 right-4 h-0.5 bg-slate-200 -z-0 hidden md:block" />
        <ol className="flex flex-col md:flex-row justify-between space-y-4 md:space-y-0 relative z-10">
          {STEPS.map((step, idx) => {
            const isCompleted = idx < currentStep || currentStatus === 'paid';
            const isCurrent = idx === currentStep && currentStatus !== 'paid';

            return (
              <li key={step.id} className="flex md:flex-col items-center md:items-center space-x-3 md:space-x-0 md:text-center flex-1">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center font-medium text-xs transition shadow-sm ${
                    isCompleted
                      ? 'bg-emerald-600 text-white'
                      : isCurrent
                      ? 'bg-emerald-50 text-emerald-700 border-2 border-emerald-600 ring-4 ring-emerald-50'
                      : 'bg-slate-100 text-slate-400 border border-slate-200'
                  }`}
                >
                  {isCompleted ? (
                    <CheckCircle2 className="w-5 h-5 text-white" />
                  ) : isCurrent ? (
                    <Clock className="w-4 h-4 text-emerald-600 animate-pulse" />
                  ) : (
                    <span>{idx + 1}</span>
                  )}
                </div>

                <div className="md:mt-2 text-left md:text-center">
                  <p
                    className={`text-xs font-semibold leading-tight ${
                      isCurrent
                        ? 'text-emerald-700'
                        : isCompleted
                        ? 'text-slate-800'
                        : 'text-slate-400'
                    }`}
                  >
                    {step.label}
                  </p>
                  <p className="text-[10px] text-slate-500 hidden lg:block mt-0.5">
                    {step.description}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
};
