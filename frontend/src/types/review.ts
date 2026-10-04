/**
 * Review Domain Types for Frontend (Phase 8.5).
 */

export interface Review {
  id: string;
  booking_id: string;
  customer_id: string;
  mechanic_id: string;
  rating: number;
  comment?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewSubmissionPayload {
  rating: number;
  comment?: string | null;
}

export interface ReviewListItem {
  id: string;
  rating: number;
  comment?: string | null;
  created_at: string;
  customer_name: string;
}

export interface MechanicReviewsList {
  items: ReviewListItem[];
  total_count: number;
  average_rating: number;
  limit: number;
  offset: number;
}
