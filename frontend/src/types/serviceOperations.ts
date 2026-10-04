/**
 * Service Operations Types (Phase 12).
 */

export interface DiagnosticFinding {
  category: string;
  finding: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  recommended_action?: string;
}

export interface RecommendedService {
  title: string;
  description?: string;
  is_required: boolean;
  estimated_price: number;
}

export interface StructuredInspection {
  id: string;
  booking_id: string;
  mechanic_id: string;
  findings: string;
  vehicle_condition?: string;
  odometer_reading?: number;
  checklist_results: Record<string, string | boolean>;
  diagnostic_findings: DiagnosticFinding[];
  recommended_services: RecommendedService[];
  parts_required: Array<{ part_name: string; quantity: number; estimated_price: number }>;
  labor_requirements?: string;
  estimated_additional_cost: number;
  evidence_file_paths: string[];
  created_at: string;
  updated_at: string;
}

export interface BookingChecklistItem {
  id: string;
  booking_id: string;
  item_key: string;
  title: string;
  category_slug: string;
  is_mandatory: boolean;
  is_completed: boolean;
  completed_at?: string;
  notes?: string;
}

export interface BookingPart {
  id: string;
  booking_id: string;
  part_name: string;
  part_number?: string;
  description?: string;
  quantity: number;
  unit_price: number;
  total_price: number;
  supplier?: string;
  warranty_months?: number;
  warranty_notes?: string;
  created_at: string;
}

export interface PriceSnapshot {
  base_service_amount: number;
  parts_total: number;
  labor_total: number;
  additional_work_total: number;
  discount_amount: number;
  taxable_base: number;
  tax_rate: number;
  tax_amount: number;
  total_amount: number;
  snapshot_timestamp: string;
  approved_by?: string;
  version: number;
}

export interface ServiceReport {
  id: string;
  booking_id: string;
  mechanic_id: string;
  summary: string;
  work_performed: string;
  recommendations?: string;
  customer_notes?: string;
  report_file_path?: string;
  parts_used: BookingPart[];
  checklist_summary: Record<string, boolean>;
  labor_summary?: string;
  final_totals: {
    subtotal: number;
    additional_charges: number;
    discount_amount: number;
    tax_amount: number;
    total_amount: number;
  };
  completed_at: string;
  created_at: string;
}
