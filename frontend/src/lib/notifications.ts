/**
 * Browser Push Notification & Service Worker Manager (Phase 15 Production Ready).
 *
 * Implements:
 * - Service worker registration (/sw.js)
 * - Permission query and interactive request
 * - Native desktop/mobile push notification presentation
 * - Graceful fallback to in-app notification toasts when permissions are denied or unsupported
 */

export type NotificationPermissionState = 'granted' | 'denied' | 'default' | 'unsupported';

export interface PushNotificationPayload {
  title: string;
  body: string;
  icon?: string;
  tag?: string;
  url?: string;
  data?: Record<string, any>;
}

export function isPushNotificationSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window && 'serviceWorker' in navigator;
}

export function getNotificationPermission(): NotificationPermissionState {
  if (!isPushNotificationSupported()) {
    return 'unsupported';
  }
  return Notification.permission as NotificationPermissionState;
}

export async function requestNotificationPermission(): Promise<NotificationPermissionState> {
  if (!isPushNotificationSupported()) {
    return 'unsupported';
  }
  try {
    const result = await Notification.requestPermission();
    return result as NotificationPermissionState;
  } catch (err) {
    console.warn('Failed to request notification permission:', err);
    return 'denied';
  }
}

let swRegistration: ServiceWorkerRegistration | null = null;

export async function registerPushServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!isPushNotificationSupported()) {
    return null;
  }

  if (swRegistration) {
    return swRegistration;
  }

  try {
    const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    swRegistration = reg;
    return reg;
  } catch (err) {
    console.warn('Service worker registration failed:', err);
    return null;
  }
}

export async function showBrowserNotification(payload: PushNotificationPayload): Promise<boolean> {
  if (!isPushNotificationSupported()) {
    return false;
  }

  if (Notification.permission !== 'granted') {
    return false;
  }

  try {
    const reg = await registerPushServiceWorker();
    if (reg && reg.showNotification) {
      await reg.showNotification(payload.title, {
        body: payload.body,
        icon: payload.icon || '/favicon.ico',
        tag: payload.tag || 'vehiclecare-alert',
        data: { url: payload.url || '/dashboard', ...(payload.data || {}) },
      });
      return true;
    } else {
      new Notification(payload.title, {
        body: payload.body,
        icon: payload.icon || '/favicon.ico',
        tag: payload.tag || 'vehiclecare-alert',
      });
      return true;
    }
  } catch (err) {
    console.warn('Could not display native notification; fallback to in-app toast:', err);
    return false;
  }
}

/**
 * Convert URL-safe base64 string to Uint8Array for VAPID applicationServerKey.
 */
export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

/**
 * Retrieve active browser push subscription if exists.
 */
export async function getPushSubscription(): Promise<PushSubscription | null> {
  const reg = await registerPushServiceWorker();
  if (!reg || !reg.pushManager) {
    return null;
  }
  try {
    return await reg.pushManager.getSubscription();
  } catch (err) {
    console.warn('Failed to retrieve push subscription:', err);
    return null;
  }
}

/**
 * Subscribe current browser to Web Push using public VAPID key.
 */
export async function subscribeUserToPush(vapidPublicKey: string): Promise<PushSubscription | null> {
  if (!vapidPublicKey || !isPushNotificationSupported()) {
    return null;
  }
  const reg = await registerPushServiceWorker();
  if (!reg || !reg.pushManager) {
    return null;
  }

  try {
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
      return existing;
    }
    const applicationServerKey = urlBase64ToUint8Array(vapidPublicKey);
    const subscription = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: applicationServerKey as unknown as BufferSource,
    });
    return subscription;
  } catch (err) {
    console.warn('Failed to subscribe user to Web Push:', err);
    return null;
  }
}

/**
 * Unsubscribe user from Web Push notifications.
 */
export async function unsubscribeUserFromPush(): Promise<boolean> {
  try {
    const subscription = await getPushSubscription();
    if (subscription) {
      return await subscription.unsubscribe();
    }
    return false;
  } catch (err) {
    console.warn('Failed to unsubscribe from push notifications:', err);
    return false;
  }
}
