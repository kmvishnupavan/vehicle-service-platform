export type UserRole = 'customer' | 'mechanic' | 'admin' | 'support';

export interface UserProfile {
  id: string;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  avatar_url?: string | null;
  role: UserRole;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

/**
 * Returns the primary home dashboard path for an authenticated role.
 */
export function getDefaultDashboardForRole(role: UserRole | string | null | undefined): string {
  switch (role) {
    case 'mechanic':
      return '/mechanic/dashboard';
    case 'admin':
    case 'support':
      return '/admin/operations';
    case 'customer':
    default:
      return '/customer/dashboard';
  }
}

/**
 * Resolves whether a user with a given role is allowed to access a route,
 * or returns the safe redirect path for unauthorized access.
 */
export function resolveRoleRoute(
  _targetPath?: string,
  user?: { role?: UserRole | string | null } | null,
  allowedRoles?: UserRole[]
): { allowed: boolean; redirectPath: string | null } {
  if (!user) {
    return { allowed: false, redirectPath: '/login' };
  }
  const role = (user.role as UserRole) || 'customer';
  const roleDashboard = getDefaultDashboardForRole(role);

  if (allowedRoles && !allowedRoles.includes(role)) {
    return { allowed: false, redirectPath: roleDashboard };
  }

  return { allowed: true, redirectPath: null };
}

/**
 * Resolves post-login redirection, guaranteeing users are never sent
 * to a portal belonging to a different role.
 */
export function resolveLoginRedirect(
  from: string | null | undefined,
  role: UserRole | string | null | undefined
): string {
  const roleDashboard = getDefaultDashboardForRole(role);
  if (!from || from === '/' || from === '/dashboard' || from === '/login') {
    return roleDashboard;
  }

  const safeRole = (role as UserRole) || 'customer';
  if (safeRole === 'customer') {
    // Customers must NEVER be directed to mechanic or admin portals
    if (from.startsWith('/mechanic') || from.startsWith('/admin')) {
      return roleDashboard;
    }
    return from;
  }

  if (safeRole === 'mechanic') {
    // Mechanics must NEVER be directed to customer or admin portals
    if (from.startsWith('/customer') || from.startsWith('/admin') || from.startsWith('/bookings')) {
      return roleDashboard;
    }
    return from;
  }

  if (safeRole === 'admin' || safeRole === 'support') {
    return from;
  }

  return roleDashboard;
}
