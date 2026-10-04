import React, { useEffect, useRef, useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { MessageSquare, ArrowDown, AlertCircle } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useChatRoom,
  useSendMessage,
  useMarkMessageRead,
  uploadChatAttachment,
  subscribeToChatChannel,
  CHAT_QUERY_KEY,
} from '../hooks/useChat';
import { ChatHeader } from '../components/chat/ChatHeader';
import { ChatMessage } from '../components/chat/ChatMessage';
import { MessageComposer } from '../components/chat/MessageComposer';
import { useAuth } from '../context/AuthContext';
import { ChatRoom } from '../types/chat';

export const BookingChatPage: React.FC = () => {
  const { bookingId } = useParams<{ bookingId: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const { data: chatRoom, isLoading, error } = useChatRoom(bookingId);
  const sendMessageMutation = useSendMessage(bookingId || '');
  const markReadMutation = useMarkMessageRead(bookingId || '');

  const [connectionStatus, setConnectionStatus] = useState<string>('CONNECTING');
  const [unreadIncomingCount, setUnreadIncomingCount] = useState<number>(0);
  const [isNearBottom, setIsNearBottom] = useState<boolean>(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Realtime channel subscription
  useEffect(() => {
    if (!bookingId || !chatRoom?.id) return;

    const channelHandle = subscribeToChatChannel({
      bookingId,
      roomId: chatRoom.id,
      onNewMessage: (newMsg) => {
        queryClient.setQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId], (old) => {
          if (!old) return old;
          // Deduplicate by ID
          if (old.messages.some((m) => m.id === newMsg.id)) {
            return old;
          }
          return {
            ...old,
            messages: [...old.messages, newMsg],
          };
        });

        // If message is from other user and we're not at the bottom, bump counter
        const isFromOther = newMsg.sender_id !== user?.id;
        if (isFromOther) {
          if (isNearBottom) {
            // Automatically mark read if near bottom
            markReadMutation.mutate(newMsg.id);
          } else {
            setUnreadIncomingCount((c) => c + 1);
          }
        }
      },
      onMessageUpdate: (updatedMsg) => {
        queryClient.setQueryData<ChatRoom>([CHAT_QUERY_KEY, bookingId], (old) => {
          if (!old) return old;
          return {
            ...old,
            messages: old.messages.map((m) => (m.id === updatedMsg.id ? updatedMsg : m)),
          };
        });
      },
      onStatusChange: (status) => {
        setConnectionStatus(status);
      },
    });

    return () => {
      channelHandle.unsubscribe();
    };
  }, [bookingId, chatRoom?.id, user?.id, isNearBottom]);

  // Mark all existing unread incoming messages as read when room loads
  useEffect(() => {
    if (!chatRoom?.messages || !user?.id) return;

    chatRoom.messages.forEach((msg) => {
      if (!msg.is_read && msg.sender_id !== user.id && !msg.isOptimistic) {
        markReadMutation.mutate(msg.id);
      }
    });
  }, [chatRoom?.id]);

  // Scroll detection to track if user has scrolled up
  const handleScroll = () => {
    if (!scrollContainerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const near = distanceFromBottom < 120;
    setIsNearBottom(near);

    if (near && unreadIncomingCount > 0) {
      setUnreadIncomingCount(0);
    }
  };

  // Scroll to bottom helper
  const scrollToBottom = (smooth = true) => {
    messagesEndRef.current?.scrollIntoView({
      behavior: smooth ? 'smooth' : 'auto',
    });
    setUnreadIncomingCount(0);
  };

  // Auto-scroll on initial load and when near bottom
  useEffect(() => {
    if (isNearBottom) {
      scrollToBottom(false);
    }
  }, [chatRoom?.messages?.length]);

  // Group messages chronologically with deduplication
  const sortedMessages = useMemo(() => {
    if (!chatRoom?.messages) return [];
    return [...chatRoom.messages].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
  }, [chatRoom?.messages]);

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 flex flex-col items-center justify-center space-y-4">
        <div className="w-10 h-10 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm font-semibold text-slate-700">Connecting to secure chat...</p>
      </div>
    );
  }

  if (error || !chatRoom) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16">
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center">
          <AlertCircle className="w-8 h-8 text-red-600 mx-auto mb-2" />
          <h2 className="font-bold text-slate-900">Chat Unavailable</h2>
          <p className="text-xs text-red-700 mt-1">
            {(error as any)?.message || 'Unable to access chat room for this booking.'}
          </p>
          <Link
            to="/dashboard"
            className="mt-4 inline-block px-4 py-2 bg-slate-900 text-white rounded-lg text-xs font-semibold"
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-2 sm:px-4 lg:px-6 py-4 sm:py-6">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden flex flex-col h-[calc(100vh-140px)] sm:h-[680px]">
        {/* Header */}
        <ChatHeader
          bookingId={chatRoom.booking_id}
          bookingNumber={chatRoom.booking_number}
          participantName={chatRoom.other_participant_name}
          participantRole={chatRoom.other_participant_role}
          connectionStatus={connectionStatus}
          canSendMessages={chatRoom.can_send_messages}
        />

        {/* Message Thread Area */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-1 bg-slate-50/50 relative"
        >
          {sortedMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center text-slate-400 py-12">
              <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center mb-3">
                <MessageSquare className="w-6 h-6" />
              </div>
              <h3 className="font-semibold text-slate-700 text-sm">Direct Service Chat</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-xs">
                Communicate directly with your assigned specialist regarding arrival, vehicle
                location, or questions.
              </p>
            </div>
          ) : (
            sortedMessages.map((msg) => {
              const isMe = msg.sender_id === user?.id || msg.sender_role === 'me';
              return (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  isMe={isMe}
                  onRetry={() =>
                    sendMessageMutation.mutate({
                      message: msg.message,
                      message_type: msg.message_type,
                      attachment_path: msg.attachment_path,
                    })
                  }
                />
              );
            })
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Floating "New Messages" Pill */}
        {unreadIncomingCount > 0 && !isNearBottom && (
          <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-20">
            <button
              onClick={() => scrollToBottom(true)}
              className="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-full bg-slate-900 text-white text-xs font-semibold shadow-lg hover:bg-slate-800 transition transform hover:scale-105"
            >
              <span>{unreadIncomingCount} new message{unreadIncomingCount > 1 ? 's' : ''}</span>
              <ArrowDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Composer */}
        <MessageComposer
          onSendMessage={async (text, attachmentPath) => {
            await sendMessageMutation.mutateAsync({
              message: text,
              message_type: attachmentPath ? 'image' : 'text',
              attachment_path: attachmentPath,
            });
            scrollToBottom(true);
          }}
          onUploadAttachment={async (file) => {
            return await uploadChatAttachment(chatRoom.booking_id, file);
          }}
          disabled={!chatRoom.can_send_messages}
          disabledReason={
            !chatRoom.can_send_messages
              ? `Chat is read-only because this booking is ${chatRoom.booking_status?.replace(/_/g, ' ')}.`
              : undefined
          }
        />
      </div>
    </div>
  );
};
