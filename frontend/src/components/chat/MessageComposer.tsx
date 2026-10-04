import React, { useState, useRef } from 'react';
import { Send, Paperclip, X, FileText, Image as ImageIcon, Loader2 } from 'lucide-react';
import { AttachmentUploadResult } from '../../types/chat';

interface Props {
  onSendMessage: (text: string, attachmentPath?: string | null) => Promise<void>;
  onUploadAttachment: (file: File) => Promise<AttachmentUploadResult>;
  disabled?: boolean;
  disabledReason?: string;
}

const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB
const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.pdf', '.txt'];

export const MessageComposer: React.FC<Props> = ({
  onSendMessage,
  onUploadAttachment,
  disabled = false,
  disabledReason,
}) => {
  const [text, setText] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [stagedAttachment, setStagedAttachment] = useState<AttachmentUploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset input
    e.target.value = '';
    setUploadError(null);

    // Validate size
    if (file.size > MAX_SIZE_BYTES) {
      setUploadError('File exceeds maximum 10 MB limit.');
      return;
    }

    // Validate extension
    const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setUploadError(`File type not allowed. Supported: ${ALLOWED_EXTENSIONS.join(', ')}`);
      return;
    }

    try {
      setIsUploading(true);
      const uploadRes = await onUploadAttachment(file);
      setStagedAttachment(uploadRes);
    } catch (err: any) {
      setUploadError(err.message || 'Failed to upload attachment.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleSend = async () => {
    const trimmed = text.trim();
    if (!trimmed && !stagedAttachment) return;
    if (isSending || isUploading || disabled) return;

    try {
      setIsSending(true);
      const attachmentPath = stagedAttachment?.attachment_path || null;
      const content = trimmed || (stagedAttachment ? `Sent an attachment: ${stagedAttachment.filename}` : '');

      await onSendMessage(content, attachmentPath);

      setText('');
      setStagedAttachment(null);
      setUploadError(null);
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    } catch {
      // Error handled by mutation/caller
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    // Auto-expand textarea up to 120px
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  };

  if (disabled) {
    return (
      <div className="p-4 bg-slate-50 border-t border-slate-200 text-center text-xs text-slate-500 font-medium">
        {disabledReason || 'Messaging is currently disabled for this booking.'}
      </div>
    );
  }

  return (
    <div className="bg-white border-t border-slate-200 p-3 sm:p-4">
      {/* Upload Error Banner */}
      {uploadError && (
        <div className="mb-2 px-3 py-1.5 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center justify-between">
          <span>{uploadError}</span>
          <button onClick={() => setUploadError(null)} className="text-red-500 hover:text-red-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Staged Attachment Preview Chip */}
      {stagedAttachment && (
        <div className="mb-2.5 inline-flex items-center space-x-2 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-1.5 text-xs text-emerald-900 shadow-xs">
          {stagedAttachment.content_type.startsWith('image/') ? (
            <ImageIcon className="w-4 h-4 text-emerald-600" />
          ) : (
            <FileText className="w-4 h-4 text-emerald-600" />
          )}
          <span className="font-semibold truncate max-w-[200px]">{stagedAttachment.filename}</span>
          <span className="text-[10px] text-emerald-600">
            ({(stagedAttachment.size_bytes / 1024).toFixed(0)} KB)
          </span>
          <button
            onClick={() => setStagedAttachment(null)}
            className="p-0.5 rounded-full hover:bg-emerald-200/60 transition text-emerald-700"
            title="Remove Attachment"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Message Input Row */}
      <div className="flex items-end space-x-2">
        {/* Hidden File Input */}
        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileSelect}
          accept=".jpg,.jpeg,.png,.webp,.pdf,.txt"
          className="hidden"
        />

        {/* Paperclip Button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading || isSending}
          className="p-2.5 rounded-xl border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition disabled:opacity-50"
          title="Attach photo or document (max 10MB)"
        >
          {isUploading ? (
            <Loader2 className="w-5 h-5 animate-spin text-emerald-600" />
          ) : (
            <Paperclip className="w-5 h-5" />
          )}
        </button>

        {/* Text Area */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            rows={1}
            value={text}
            onChange={handleTextChange}
            onKeyDown={handleKeyDown}
            placeholder={
              isUploading
                ? 'Uploading media...'
                : 'Type a message... (Enter to send, Shift+Enter for new line)'
            }
            disabled={isSending}
            className="w-full resize-none rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:border-emerald-500 focus:ring-2 focus:ring-emerald-50 max-h-32 transition leading-relaxed"
          />
        </div>

        {/* Send Button */}
        <button
          type="button"
          onClick={handleSend}
          disabled={(!text.trim() && !stagedAttachment) || isSending || isUploading}
          className="p-2.5 rounded-xl bg-emerald-600 text-white font-semibold hover:bg-emerald-700 transition disabled:opacity-40 disabled:cursor-not-allowed shadow-sm flex-shrink-0"
          title="Send Message"
        >
          {isSending ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </button>
      </div>
    </div>
  );
};
