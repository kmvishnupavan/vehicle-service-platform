/**
 * Mechanic Dashboard TypeScript Interfaces (Phase 8.6).
 *
 * Types for Overview, Performance, Earnings, Recent Jobs, and Reviews.
 */

export interface TodayJobs {
  jobs: number;
  completed: number;
  cancelled: number;
}

export interface DashboardOverview {
  today: TodayJobs;
  active_jobs: number;
  completed_jobs: number;
  cancelled_jobs: number;
  total_earnings: string;
  pending_earnings: string;
  average_rating: number;
  review_count: number;
  completion_rate: number;
}

export interface MonthlyBreakdown {
  month: string;
  completed: number;
  cancelled: number;
  earnings: string;
}

export interface MechanicPerformance {
  total_jobs: number;
  completed_jobs: number;
  cancelled_jobs: number;
  active_jobs: number;
  completion_rate: number;
  average_rating: number;
  review_count: number;
  rating_distribution: {
    '1': number;
    '2': number;
    '3': number;
    '4': number;
    '5': number;
    [key: string]: number;
  };
  monthly_breakdown: MonthlyBreakdown[];
}

export interface EarningsItem {
  booking_id: string;
  booking_number: string;
  completed_at?: string | null;
  gross_amount: string;
  additional_work_amount: string;
  deductions: string;
  net_amount: string;
  payment_status: 'paid' | 'pending' | 'refunded' | 'failed' | 'unpaid' | string;
  paid_at?: string | null;
}

export interface EarningsList {
  items: EarningsItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecentJobItem {
  booking_id: string;
  booking_number: string;
  service_summary: string;
  vehicle_summary: string;
  booking_status: string;
  assignment_status: string;
  scheduled_at: string;
  amount: string;
  payment_status: string;
}

export interface RecentJobsList {
  items: RecentJobItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecentReviewItem {
  id: string;
  booking_id: string;
  rating: number;
  review_text?: string | null;
  customer_name: string;
  created_at: string;
}

export interface RecentReviewsList {
  items: RecentReviewItem[];
  total: number;
  limit: number;
  offset: number;
}

export type DateFilterPreset = 'today' | '7d' | '30d' | 'month' | 'custom' | 'all';

export interface DashboardDateFilters {
  preset: DateFilterPreset;
  fromDate?: string;
  toDate?: string;
}
