/**
 * Browser Supabase Client Singleton.
 *
 * Configured strictly with the public/publishable key.
 * Used exclusively for browser auth state management and Realtime channel subscriptions.
 * NEVER imports or references service role keys.
 */

import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://dfigtryvvujhwuiyzdvs.supabase.co';
const supabasePublishableKey =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || 'sb_publishable_OZdsss6XPdfV3SLTqlKncw_BKqgJAMn';

if (!supabaseUrl || !supabasePublishableKey) {
  console.warn('Missing Supabase frontend configuration. Realtime and auth may fail.');
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
