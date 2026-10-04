import { Page } from '@playwright/test';

export interface MockUserConfig {
  id: string;
  email: string;
  role: 'customer' | 'mechanic' | 'admin';
  full_name: string;
}

export const MOCK_USERS = {
  customer: {
    id: '11111111-1111-1111-1111-111111111111',
    email: 'customer@example.com',
    role: 'customer' as const,
    full_name: 'John Customer',
  },
  mechanic: {
    id: '66666666-6666-6666-6666-666666666666',
    email: 'mechanic@example.com',
    role: 'mechanic' as const,
    full_name: 'Mike Mechanic',
  },
  admin: {
    id: '55555555-5555-5555-5555-555555555555',
    email: 'admin@example.com',
    role: 'admin' as const,
    full_name: 'Alex Admin',
  },
};

export async function setupAuthenticatedSession(page: Page, user: MockUserConfig) {
  const sessionData = {
    access_token: `mock-jwt-token-for-${user.role}`,
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    refresh_token: 'mock-refresh-token',
    user: {
      id: user.id,
      aud: 'authenticated',
      role: 'authenticated',
      email: user.email,
      email_confirmed_at: new Date().toISOString(),
      user_metadata: {
        full_name: user.full_name,
        role: user.role,
      },
      app_metadata: {
        role: user.role,
      },
    },
  };

  // Pre-seed localStorage before any page scripts run
  await page.addInitScript(
    ({ session }) => {
      const storageKey = 'sb-dfigtryvvujhwuiyzdvs-auth-token';
      window.localStorage.setItem(storageKey, JSON.stringify(session));
      // Also write common supabase keys
      window.localStorage.setItem('supabase.auth.token', JSON.stringify(session));
    },
    { session: sessionData }
  );
}
