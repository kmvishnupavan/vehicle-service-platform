/**
 * Customer-Friendly Booking Status Formatter (Phase 11).
 *
 * Translates raw database state machine keys into clear, human-centered operational messages.
 * Prevents exposing internal state names directly to customers.
 */

export interface FriendlyBookingStatus {
  title: string;
  subtitle: string;
  badgeText: string;
  colorClass: string;
  badgeClass: string;
}

export const getFriendlyBookingStatus = (rawStatus: string): FriendlyBookingStatus => {
  switch (rawStatus) {
    case 'pending':
    case 'searching_mechanic':
      return {
        title: 'Finding nearby mechanics...',
        subtitle: 'Locating qualified technicians in your service area.',
        badgeText: 'Searching',
        colorClass: 'text-amber-600',
        badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',
      };
    case 'mechanic_assigned':
      return {
        title: 'Mechanic found',
        subtitle: 'A technician has accepted your request and is preparing for dispatch.',
        badgeText: 'Mechanic Assigned',
        colorClass: 'text-blue-600',
        badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
      };
    case 'mechanic_en_route':
      return {
        title: 'Your mechanic is on the way',
        subtitle: 'Live GPS tracking is now active. Follow your technician on the map.',
        badgeText: 'En Route',
        colorClass: 'text-indigo-600',
        badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      };
    case 'mechanic_arrived':
      return {
        title: 'Your mechanic has arrived',
        subtitle: 'Technician has reached your doorstep address.',
        badgeText: 'Arrived',
        colorClass: 'text-emerald-600',
        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      };
    case 'inspection':
      return {
        title: 'Vehicle inspection in progress',
        subtitle: 'Initial safety and condition diagnostics are currently underway.',
        badgeText: 'Inspection',
        colorClass: 'text-purple-600',
        badgeClass: 'bg-purple-50 text-purple-700 border-purple-200',
      };
    case 'awaiting_customer_approval':
    case 'additional_work':
      return {
        title: 'Additional work requires your approval',
        subtitle: 'Review recommended parts or tasks before work proceeds.',
        badgeText: 'Approval Required',
        colorClass: 'text-amber-700',
        badgeClass: 'bg-amber-100 text-amber-800 border-amber-300',
      };
    case 'service_in_progress':
      return {
        title: 'Service in progress',
        subtitle: 'Technician is actively servicing your vehicle.',
        badgeText: 'In Progress',
        colorClass: 'text-emerald-700',
        badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      };
    case 'service_completed':
    case 'payment_pending':
      return {
        title: 'Service completed',
        subtitle: 'Service work is finished. Please review invoice and complete payment.',
        badgeText: 'Completed',
        colorClass: 'text-emerald-800',
        badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      };
    case 'paid':
      return {
        title: 'Paid & Completed',
        subtitle: 'Thank you for choosing VehicleCare doorstep service.',
        badgeText: 'Paid',
        colorClass: 'text-emerald-900',
        badgeClass: 'bg-emerald-100 text-emerald-900 border-emerald-300',
      };
    case 'cancelled':
      return {
        title: 'Booking cancelled',
        subtitle: 'This service booking was cancelled.',
        badgeText: 'Cancelled',
        colorClass: 'text-rose-700',
        badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',
      };
    case 'disputed':
      return {
        title: 'Under dispute review',
        subtitle: 'Platform operations is reviewing this booking.',
        badgeText: 'Disputed',
        colorClass: 'text-rose-800',
        badgeClass: 'bg-rose-100 text-rose-800 border-rose-300',
      };
    default:
      return {
        title: rawStatus.replace(/_/g, ' '),
        subtitle: '',
        badgeText: rawStatus.replace(/_/g, ' '),
        colorClass: 'text-slate-700',
        badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
      };
  }
};
