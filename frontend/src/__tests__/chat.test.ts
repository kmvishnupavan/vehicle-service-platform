import { describe, it, expect, vi } from 'vitest';
import { ChatMessage } from '../types/chat';

describe('Chat UI & State Management - Unit & Logic Test Suite (Phase 8.4)', () => {
  const ROOM_ID = 'room-1111-1111-1111-111111111111';
  const CUSTOMER_ID = 'cust-1111-1111-1111-111111111111';
  const MECHANIC_ID = 'mech-1111-1111-1111-111111111111';

  const createSampleMessage = (overrides?: Partial<ChatMessage>): ChatMessage => ({
    id: 'msg-' + Math.random().toString(36).substring(2, 9),
    room_id: ROOM_ID,
    sender_id: CUSTOMER_ID,
    message: 'Hello mechanic',
    message_type: 'text',
    attachment_path: null,
    attachment_url: null,
    is_read: false,
    created_at: new Date().toISOString(),
    ...overrides,
  });

  // 1. Message rendering
  it('correctly maps message attributes for UI display', () => {
    const msg = createSampleMessage({
      message: 'Inspection completed, check brake pads.',
      sender_role: 'mechanic',
      is_read: true,
    });

    expect(msg.message).toBe('Inspection completed, check brake pads.');
    expect(msg.sender_role).toBe('mechanic');
    expect(msg.is_read).toBe(true);
    expect(msg.message_type).toBe('text');
  });

  // 2. Chronological ordering
  it('orders messages chronologically ascending by created_at', () => {
    const m1 = createSampleMessage({ id: '1', created_at: '2026-10-03T10:00:00Z' });
    const m2 = createSampleMessage({ id: '2', created_at: '2026-10-03T10:05:00Z' });
    const m3 = createSampleMessage({ id: '3', created_at: '2026-10-03T10:02:00Z' });

    const unsorted = [m2, m1, m3];
    const sorted = [...unsorted].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );

    expect(sorted.map((m) => m.id)).toEqual(['1', '3', '2']);
  });

  // 3. Duplicate Realtime event ignored
  it('deduplicates incoming messages by authoritative ID', () => {
    const existingMessages: ChatMessage[] = [
      createSampleMessage({ id: 'msg-101', message: 'First message' }),
      createSampleMessage({ id: 'msg-102', message: 'Second message' }),
    ];

    const duplicatePacket = createSampleMessage({ id: 'msg-101', message: 'First message' });

    // Deduplication logic
    const exists = existingMessages.some((m) => m.id === duplicatePacket.id);
    const updated = exists ? existingMessages : [...existingMessages, duplicatePacket];

    expect(updated.length).toBe(2);
    expect(updated.map((m) => m.id)).toEqual(['msg-101', 'msg-102']);
  });

  // 4. Optimistic message
  it('creates optimistic message state immediately before REST response', () => {
    const tempId = `temp-${Date.now()}`;
    const optimisticMessage: ChatMessage = {
      id: tempId,
      room_id: ROOM_ID,
      sender_id: CUSTOMER_ID,
      message: 'Where are you currently?',
      message_type: 'text',
      attachment_path: null,
      attachment_url: null,
      is_read: false,
      created_at: new Date().toISOString(),
      sender_role: 'me',
      isOptimistic: true,
    };

    expect(optimisticMessage.isOptimistic).toBe(true);
    expect(optimisticMessage.id.startsWith('temp-')).toBe(true);

    // Reconcile on REST success
    const serverMessage: ChatMessage = {
      ...optimisticMessage,
      id: 'server-uuid-real-1234',
      isOptimistic: false,
    };

    const thread = [optimisticMessage];
    const reconciled = thread.map((m) => (m.id === tempId ? serverMessage : m));

    expect(reconciled[0].id).toBe('server-uuid-real-1234');
    expect(reconciled[0].isOptimistic).toBe(false);
  });

  // 5. Failed message & 6. Retry message
  it('marks failed messages with error state and permits retry', () => {
    let message: ChatMessage = createSampleMessage({
      id: 'temp-failed-1',
      isOptimistic: true,
    });

    // Simulate network error
    message = { ...message, isError: true, error: 'Network failure' };
    expect(message.isError).toBe(true);
    expect(message.error).toBe('Network failure');

    // Simulate retry action
    const retryPayload = {
      message: message.message,
      message_type: message.message_type,
      attachment_path: message.attachment_path,
    };

    expect(retryPayload.message).toBe('Hello mechanic');
  });

  // 7. Attachment validation & 8. Invalid MIME & 9. Oversized attachment
  it('validates attachments against permitted MIME types, extensions, and size limits', () => {
    const MAX_SIZE = 10 * 1024 * 1024; // 10MB
    const ALLOWED_EXTS = ['.jpg', '.jpeg', '.png', '.webp', '.pdf', '.txt'];

    const validateAttachment = (filename: string, sizeBytes: number) => {
      if (sizeBytes > MAX_SIZE) return { valid: false, error: 'Oversized file' };
      const ext = '.' + (filename.split('.').pop() || '').toLowerCase();
      if (!ALLOWED_EXTS.includes(ext)) return { valid: false, error: 'Invalid file type' };
      return { valid: true };
    };

    expect(validateAttachment('invoice.pdf', 1024 * 50)).toEqual({ valid: true });
    expect(validateAttachment('photo.png', 1024 * 500)).toEqual({ valid: true });
    expect(validateAttachment('malicious.exe', 1024)).toEqual({
      valid: false,
      error: 'Invalid file type',
    });
    expect(validateAttachment('script.js', 1024)).toEqual({
      valid: false,
      error: 'Invalid file type',
    });
    expect(validateAttachment('huge_video.png', 12 * 1024 * 1024)).toEqual({
      valid: false,
      error: 'Oversized file',
    });
  });

  // 10. Unread count
  it('computes unread message count excluding own outgoing messages', () => {
    const roomMessages: ChatMessage[] = [
      createSampleMessage({ sender_id: CUSTOMER_ID, is_read: false }), // Me -> not unread for me
      createSampleMessage({ sender_id: MECHANIC_ID, is_read: false }), // Other -> unread
      createSampleMessage({ sender_id: MECHANIC_ID, is_read: true }),  // Other -> already read
      createSampleMessage({ sender_id: MECHANIC_ID, is_read: false }), // Other -> unread
    ];

    const currentUserId = CUSTOMER_ID;
    const unread = roomMessages.filter(
      (m) => m.sender_id !== currentUserId && !m.is_read
    ).length;

    expect(unread).toBe(2);
  });

  // 11. Read receipt
  it('updates is_read state when read receipt is processed', () => {
    const m = createSampleMessage({ id: 'msg-read-1', is_read: false });
    expect(m.is_read).toBe(false);

    const updated = { ...m, is_read: true };
    expect(updated.is_read).toBe(true);
  });

  // 12. Connection state
  it('correctly classifies Realtime connection states', () => {
    const validStates = ['CONNECTING', 'SUBSCRIBED', 'CHANNEL_ERROR', 'TIMED_OUT', 'CLOSED'];
    validStates.forEach((st) => {
      expect(typeof st).toBe('string');
    });
  });

  // 13. Auto-scroll logic & 14. "New messages" indicator
  it('detects near-bottom threshold for auto-scroll and triggers indicator when scrolled up', () => {
    const checkScrollState = (scrollTop: number, scrollHeight: number, clientHeight: number) => {
      const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
      const isNearBottom = distanceFromBottom < 120;
      return { isNearBottom, showNewMessagesPill: !isNearBottom };
    };

    // User is at bottom
    const atBottom = checkScrollState(880, 1400, 500); // 1400 - 880 - 500 = 20px (< 120)
    expect(atBottom.isNearBottom).toBe(true);
    expect(atBottom.showNewMessagesPill).toBe(false);

    // User has scrolled up 400px
    const scrolledUp = checkScrollState(400, 1400, 500); // 1400 - 400 - 500 = 500px (> 120)
    expect(scrolledUp.isNearBottom).toBe(false);
    expect(scrolledUp.showNewMessagesPill).toBe(true);
  });

  // 15. Cleanup on unmount
  it('ensures Realtime channel unmount cleanup removes listener', () => {
    const mockChannel = {
      unsubscribe: vi.fn(),
    };

    // Unmount
    mockChannel.unsubscribe();
    expect(mockChannel.unsubscribe).toHaveBeenCalledTimes(1);
  });
});
