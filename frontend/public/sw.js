// ==============================================================================
// VehicleCare Service Worker - Web Push & Background Notifications
// Production HTTPS-compliant Service Worker
// ==============================================================================

const CACHE_NAME = 'vehiclecare-sw-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// Handle incoming Web Push notifications
self.addEventListener('push', (event) => {
  if (!event.data) {
    return;
  }

  let payload;
  try {
    payload = event.data.json();
  } catch (err) {
    payload = {
      title: 'VehicleCare Update',
      body: event.data.text() || 'Service appointment status update received.',
      data: { url: '/dashboard' },
    };
  }

  const title = payload.title || 'VehicleCare Notification';
  const options = {
    body: payload.body || payload.message || 'You have an operational service update.',
    icon: payload.icon || '/favicon.ico',
    badge: payload.badge || '/favicon.ico',
    tag: payload.tag || 'vehiclecare-service-alert',
    renotify: true,
    data: payload.data || { url: '/dashboard' },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// Handle user clicking on a native browser notification
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || '/dashboard';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Focus existing window if available
      for (const client of clientList) {
        if (client.url.includes(targetUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      // Otherwise open new window
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
