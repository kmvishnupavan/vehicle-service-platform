/**
 * Chat Types and Contracts (Phase 8.4).
 */

export type MessageType = 'text' | 'image' | 'file' | 'system' | 'location';

export interface ChatMessage {
  id: string;
  room_id: string;
  sender_id: string;
  message: string;
  message_type: MessageType;
  attachment_path: string | null;
  attachment_url: string | null;
  is_read: boolean;
  created_at: string;
  sender_role?: 'me' | 'customer' | 'mechanic' | 'admin';
  sender_name?: string | null;
  // Optimistic & local delivery state
  isOptimistic?: boolean;
  isError?: boolean;
  error?: string;
}

export interface ChatRoom {
  id: string;
  booking_id: string;
  customer_id: string;
  mechanic_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  other_participant_name: string | null;
  other_participant_role: string | null;
  booking_number: string | null;
  booking_status: string | null;
  can_send_messages: boolean;
  messages: ChatMessage[];
  unread_count: number;
}

export interface ChatAttachmentRules {
  bucket: string;
  path_pattern: string;
  max_file_size_bytes: number;
  allowed_mime_types: string[];
  allowed_extensions: string[];
  disallowed_extensions: string[];
}

export interface AttachmentUploadResult {
  attachment_path: string;
  signed_url: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}
