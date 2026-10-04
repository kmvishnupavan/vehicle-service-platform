import React, { useState } from 'react';
import {
  Check,
  CheckCheck,
  Clock,
  AlertCircle,
  FileText,
  Download,
  ExternalLink,
  X,
} from 'lucide-react';
import { ChatMessage as ChatMessageType } from '../../types/chat';

interface Props {
  message: ChatMessageType;
  isMe: boolean;
  onRetry?: () => void;
}

export const ChatMessage: React.FC<Props> = ({ message, isMe, onRetry }) => {
  const [showImageModal, setShowImageModal] = useState(false);

  const formattedTime = new Date(message.created_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  });

  const isImage =
    message.message_type === 'image' ||
    (message.attachment_path &&
      /\.(jpg|jpeg|png|webp)$/i.test(message.attachment_path));

  const isPdfOrDoc =
    message.message_type === 'file' ||
    (message.attachment_path &&
      /\.(pdf|txt)$/i.test(message.attachment_path));

  return (
    <div className={`flex flex-col ${isMe ? 'items-end' : 'items-start'} mb-3`}>
      <div
        className={`max-w-[85%] sm:max-w-[70%] rounded-2xl px-4 py-2.5 text-xs sm:text-sm shadow-sm transition ${
          isMe
            ? 'bg-emerald-600 text-white rounded-br-xs'
            : 'bg-white text-slate-800 border border-slate-200 rounded-bl-xs'
        } ${message.isError ? 'border-red-400 bg-red-50 text-red-900' : ''}`}
      >
        {/* Attachment: Image Preview */}
        {isImage && (message.attachment_url || message.attachment_path) && (
          <div className="mb-2">
            <img
              src={message.attachment_url || '#'}
              alt="Attachment"
              onClick={() => message.attachment_url && setShowImageModal(true)}
              className="max-h-48 rounded-xl object-cover cursor-pointer hover:opacity-95 transition border border-black/10"
              loading="lazy"
            />
          </div>
        )}

        {/* Attachment: Document / PDF */}
        {isPdfOrDoc && (message.attachment_url || message.attachment_path) && (
          <div
            className={`flex items-center space-x-2.5 p-2 rounded-xl mb-2 text-xs ${
              isMe ? 'bg-emerald-700/60 text-white' : 'bg-slate-50 text-slate-700 border border-slate-200'
            }`}
          >
            <FileText className="w-5 h-5 flex-shrink-0" />
            <div className="flex-1 truncate">
              <span className="font-semibold block truncate">
                {message.attachment_path?.split('/').pop() || 'Document.pdf'}
              </span>
              <span className="text-[10px] opacity-80">Media Document</span>
            </div>
            {message.attachment_url && (
              <a
                href={message.attachment_url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1 rounded-md hover:bg-black/10 transition"
                title="View / Download"
              >
                <Download className="w-4 h-4" />
              </a>
            )}
          </div>
        )}

        {/* Text Content */}
        <p className="whitespace-pre-wrap break-words leading-relaxed">{message.message}</p>

        {/* Metadata Footer: Timestamp + Delivery / Read State */}
        <div
          className={`flex items-center justify-end space-x-1 mt-1 text-[10px] ${
            isMe ? 'text-emerald-100' : 'text-slate-400'
          }`}
        >
          <span>{formattedTime}</span>

          {isMe && (
            <span className="inline-flex items-center ml-0.5">
              {message.isError ? (
                <button
                  onClick={onRetry}
                  className="flex items-center text-red-600 font-bold hover:underline"
                  title="Retry sending message"
                >
                  <AlertCircle className="w-3 h-3 mr-0.5" />
                  Retry
                </button>
              ) : message.isOptimistic ? (
                <span title="Sending...">
                  <Clock className="w-3 h-3 text-emerald-200 animate-pulse" />
                </span>
              ) : message.is_read ? (
                <span title="Read">
                  <CheckCheck className="w-3.5 h-3.5 text-blue-200" />
                </span>
              ) : (
                <span title="Sent">
                  <Check className="w-3.5 h-3.5 text-emerald-200" />
                </span>
              )}
            </span>
          )}
        </div>
      </div>

      {/* Modal: Fullscreen Image Preview */}
      {showImageModal && message.attachment_url && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-xs flex items-center justify-center p-4"
          onClick={() => setShowImageModal(false)}
        >
          <div
            className="relative max-w-3xl max-h-[90vh] bg-slate-900 rounded-2xl overflow-hidden shadow-2xl p-2"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setShowImageModal(false)}
              className="absolute top-3 right-3 p-1.5 rounded-full bg-black/60 text-white hover:bg-black/80 transition z-10"
              title="Close Preview"
            >
              <X className="w-5 h-5" />
            </button>
            <img
              src={message.attachment_url}
              alt="Full Preview"
              className="max-h-[80vh] w-auto mx-auto object-contain rounded-xl"
            />
            <div className="flex justify-end p-2">
              <a
                href={message.attachment_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center text-xs font-semibold text-white/80 hover:text-white"
              >
                <ExternalLink className="w-3.5 h-3.5 mr-1" />
                Open original in new tab
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
