/**
 * Chat React Hooks (Phase 8.4).
 *
 * Provides TanStack Query hooks, optimistic message dispatch, read receipts,
 * media attachment uploads, and Supabase Realtime channel subscription.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { supabase } from '../lib/supabase';
import {
  ChatMessage,
  ChatRoom,
  AttachmentUploadResult,
  UnreadCountResponse,
  MessageType,
} from '../types/chat';

export const CHAT_QUERY_KEY = 'chat-room';
export const UNREAD_COUNT_KEY = 'chat-unread-count';

/**
 * Fetch authorized booking chat room and messages.
 */
export function useChatRoom(bookingId: string | undefined) {
  return useQuery<ChatRoom, Error>({
    queryKey: [CHAT_QUERY_KEY, bookingId],
    queryFn: async () => {
      if (!bookingId) throw new Error('Booking ID is required.');
      return await api.get<ChatRoom>(`/bookings/${bookingId}/chat`);
    },
    enabled: Boolean(bookingId),
    staleTime: 1000 * 30, // 30 seconds fresh; realtime events update cache immediately
  });
}

/**
 * Fetch total unread chat count across bookings for the current user.
 */
export function useUnreadChatCount() {
  return useQuery<UnreadCountResponse, Error>({
    queryKey: [UNREAD_COUNT_KEY],
    queryFn: async () => {
      return await api.get<UnreadCountResponse>('/chat/unread-count');
    },
    staleTime: 1000 * 60,
  });
}

/**
 * Send message mutation with optimistic UI and error reconciliation.
 */
export function useSendMessage(bookingId: string) {
  const queryClient = useQueryClient();

  return useMutation<
    ChatMessage,
    Error,
    { message: string; message_type?: MessageType; attachment_path?: string | null },
    { tempId: string; previousRoom?: ChatRoom }
  >({
    mutationFn: async ({ message, message_type = 'text', attachment_path }) => {
      return await api.post<ChatMessage>(`/bookings/${bookingId}/chat/messages`, {
        message,
        message_type,
        attachment_path,
      });
    },
    onMutate: async ({ message, message_type = 'text', attachment_path }) => {
      await queryClient.cancelQueries({ queryKey: [CHAT_QUERY_KEY, bookingId] });
      const previousRoom = queryClient.getQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId]);

      const tempId = `temp-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
      const optimisticMsg: ChatMessage = {
        id: tempId,
        room_id: previousRoom?.id || '',
        sender_id: previousRoom?.customer_id || '',
        message,
        message_type,
        attachment_path: attachment_path || null,
        attachment_url: null,
        is_read: false,
        created_at: new Date().toISOString(),
        sender_role: 'me',
        isOptimistic: true,
      };

      if (previousRoom) {
        queryClient.setQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId], {
          ...previousRoom,
          messages: [...previousRoom.messages, optimisticMsg],
        });
      }

      return { tempId, previousRoom };
    },
    onError: (_err, _vars, context) => {
      if (context?.tempId && context?.previousRoom) {
        // Mark optimistic message as failed rather than silently dropping
        const currentData = queryClient.getQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId]);
        if (currentData) {
          queryClient.setQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId], {
            ...currentData,
            messages: currentData.messages.map((m) =>
              m.id === context.tempId ? { ...m, isError: true, error: 'Failed to send' } : m
            ),
          });
        }
      }
    },
    onSuccess: (savedMessage, _vars, context) => {
      const currentData = queryClient.getQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId]);
      if (currentData) {
        // Replace temp optimistic message with authoritative server record
        const updated = currentData.messages
          .map((m) => (m.id === context?.tempId ? savedMessage : m))
          .filter((m, idx, arr) => arr.findIndex((x) => x.id === m.id) === idx); // Deduplicate

        queryClient.setQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId], {
          ...currentData,
          messages: updated,
        });
      }
    },
  });
}

/**
 * Mark a message as read mutation.
 */
export function useMarkMessageRead(bookingId: string) {
  const queryClient = useQueryClient();

  return useMutation<{ success: boolean; message_id: string; is_read: boolean }, Error, string>({
    mutationFn: async (messageId: string) => {
      return await api.post(`/chat/messages/${messageId}/read`);
    },
    onSuccess: (data) => {
      const currentData = queryClient.getQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId]);
      if (currentData) {
        queryClient.setQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId], {
          ...currentData,
          messages: currentData.messages.map((m) =>
            m.id === data.message_id ? { ...m, is_read: true } : m
          ),
          unread_count: Math.max(0, currentData.unread_count - 1),
        });
      }
      queryClient.invalidateQueries({ queryKey: [UNREAD_COUNT_KEY] });
    },
  });
}

/**
 * Upload chat media attachment.
 */
export async function uploadChatAttachment(
  bookingId: string,
  file: File
): Promise<AttachmentUploadResult> {
  const formData = new FormData();
  formData.append('file', file);

  const { data: sessionData } = await supabase.auth.getSession();
  const token = sessionData?.session?.access_token;
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

  const res = await fetch(`${baseUrl}/bookings/${bookingId}/chat/attachments/upload`, {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new Error(errorBody.detail || 'Failed to upload attachment.');
  }

  return (await res.json()) as AttachmentUploadResult;
}

/**
 * Subscribe to Supabase Realtime channel for booking chat messages.
 */
export function subscribeToChatChannel({
  bookingId,
  roomId,
  onNewMessage,
  onMessageUpdate,
  onStatusChange,
}: {
  bookingId: string;
  roomId: string;
  onNewMessage: (message: ChatMessage) => void;
  onMessageUpdate?: (message: ChatMessage) => void;
  onStatusChange?: (status: string) => void;
}) {
  const channelName = `booking-chat:${bookingId}`;

  const channel = supabase.channel(channelName, {
    config: {
      private: true,
      broadcast: { ack: false },
    },
  });

  // Listen to postgres_changes on chat_messages table
  channel
    .on(
      'postgres_changes',
      {
        event: 'INSERT',
        schema: 'public',
        table: 'chat_messages',
        filter: `room_id=eq.${roomId}`,
      },
      (payload) => {
        if (payload.new) {
          const raw = payload.new as any;
          const msg: ChatMessage = {
            id: raw.id,
            room_id: raw.room_id,
            sender_id: raw.sender_id,
            message: raw.message,
            message_type: raw.message_type,
            attachment_path: raw.attachment_path,
            attachment_url: null,
            is_read: raw.is_read,
            created_at: raw.created_at,
          };
          onNewMessage(msg);
        }
      }
    )
    .on(
      'postgres_changes',
      {
        event: 'UPDATE',
        schema: 'public',
        table: 'chat_messages',
        filter: `room_id=eq.${roomId}`,
      },
      (payload) => {
        if (payload.new && onMessageUpdate) {
          const raw = payload.new as any;
          const msg: ChatMessage = {
            id: raw.id,
            room_id: raw.room_id,
            sender_id: raw.sender_id,
            message: raw.message,
            message_type: raw.message_type,
            attachment_path: raw.attachment_path,
            attachment_url: null,
            is_read: raw.is_read,
            created_at: raw.created_at,
          };
          onMessageUpdate(msg);
        }
      }
    );

  channel.subscribe((status, _err) => {
    if (onStatusChange) {
      onStatusChange(status);
    }
  });

  return {
    unsubscribe: () => {
      supabase.removeChannel(channel);
    },
  };
}
