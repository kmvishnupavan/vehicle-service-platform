/**
 * Browser Supabase Client Singleton.
 *
 * Configured strictly with the public/publishable key.
 * Used exclusively for browser auth state management and Realtime channel subscriptions.
 * NEVER imports or references service role keys.
 */

import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://placeholder-project.supabase.co';
const supabasePublishableKey =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || 'placeholder_publishable_key';

if (!import.meta.env.VITE_SUPABASE_URL || !import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY) {
  console.warn('Missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY. Please configure your environment variables.');
}

export const supabase = createClient(supabaseUrl, supabasePublishableKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
  },
});
