import { describe, it, expect } from 'vitest';
import {
  UserRole,
  UserProfile,
  getDefaultDashboardForRole,
  resolveRoleRoute,
  resolveLoginRedirect,
} from '../types/user';

describe('Role-Based Routing and Access Control', () => {
  // Test Case 1: Customer login -> customer dashboard
  it('1. redirects Customer login to /customer/dashboard', () => {
    const role: UserRole = 'customer';
    const target = getDefaultDashboardForRole(role);
    expect(target).toBe('/customer/dashboard');

    const redirect = resolveLoginRedirect(undefined, role);
    expect(redirect).toBe('/customer/dashboard');

    const redirectFromRoot = resolveLoginRedirect('/', role);
    expect(redirectFromRoot).toBe('/customer/dashboard');
  });

  // Test Case 2: Mechanic login -> mechanic dashboard
  it('2. redirects Mechanic login to /mechanic/dashboard', () => {
    const role: UserRole = 'mechanic';
    const target = getDefaultDashboardForRole(role);
    expect(target).toBe('/mechanic/dashboard');

    const redirect = resolveLoginRedirect(undefined, role);
    expect(redirect).toBe('/mechanic/dashboard');

    const redirectFromRoot = resolveLoginRedirect('/', role);
    expect(redirectFromRoot).toBe('/mechanic/dashboard');
  });

  // Test Case 3: Admin login -> admin dashboard
  it('3. redirects Admin login to /admin/operations', () => {
    const role: UserRole = 'admin';
    const target = getDefaultDashboardForRole(role);
    expect(target).toBe('/admin/operations');

    const redirect = resolveLoginRedirect(undefined, role);
    expect(redirect).toBe('/admin/operations');

    const redirectFromRoot = resolveLoginRedirect('/', role);
    expect(redirectFromRoot).toBe('/admin/operations');
  });

  // Test Case 4: Customer cannot access mechanic dashboard
  it('4. prevents Customer from accessing mechanic dashboard and redirects to /customer/dashboard', () => {
    const customerUser = { role: 'customer' as UserRole };
    const result = resolveRoleRoute('/mechanic/dashboard', customerUser, ['mechanic']);

    expect(result.allowed).toBe(false);
    expect(result.redirectPath).toBe('/customer/dashboard');

    // Also verify login redirect does not retain mechanic path for a customer
    const loginRedirect = resolveLoginRedirect('/mechanic/dashboard', 'customer');
    expect(loginRedirect).toBe('/customer/dashboard');
  });

  // Test Case 5: Mechanic cannot access customer dashboard
  it('5. prevents Mechanic from accessing customer dashboard and redirects to /mechanic/dashboard', () => {
    const mechanicUser = { role: 'mechanic' as UserRole };
    const result = resolveRoleRoute('/customer/dashboard', mechanicUser, ['customer', 'admin']);

    expect(result.allowed).toBe(false);
    expect(result.redirectPath).toBe('/mechanic/dashboard');

    // Also verify login redirect does not retain customer path for a mechanic
    const loginRedirect = resolveLoginRedirect('/customer/dashboard', 'mechanic');
    expect(loginRedirect).toBe('/mechanic/dashboard');
  });

  // Test Case 6: Unauthenticated user -> redirects to /login
  it('6. redirects unauthenticated user to /login', () => {
    const unauthenticatedUser = null;
    const resultCustomer = resolveRoleRoute('/customer/dashboard', unauthenticatedUser, ['customer']);
    expect(resultCustomer.allowed).toBe(false);
    expect(resultCustomer.redirectPath).toBe('/login');

    const resultMechanic = resolveRoleRoute('/mechanic/dashboard', unauthenticatedUser, ['mechanic']);
    expect(resultMechanic.allowed).toBe(false);
    expect(resultMechanic.redirectPath).toBe('/login');

    const resultAdmin = resolveRoleRoute('/admin/operations', unauthenticatedUser, ['admin']);
    expect(resultAdmin.allowed).toBe(false);
    expect(resultAdmin.redirectPath).toBe('/login');
  });

  // Test Case 7: Session restoration preserves correct role
  it('7. preserves correct role during session restoration', () => {
    const customerProfile: UserProfile = {
      id: 'cust-123',
      full_name: 'Jane Customer',
      role: 'customer',
      is_active: true,
    };
    expect(getDefaultDashboardForRole(customerProfile.role)).toBe('/customer/dashboard');

    const mechanicProfile: UserProfile = {
      id: 'mech-456',
      full_name: 'John Mechanic',
      role: 'mechanic',
      is_active: true,
    };
    expect(getDefaultDashboardForRole(mechanicProfile.role)).toBe('/mechanic/dashboard');

    const adminProfile: UserProfile = {
      id: 'admin-789',
      full_name: 'Admin User',
      role: 'admin',
      is_active: true,
    };
    expect(getDefaultDashboardForRole(adminProfile.role)).toBe('/admin/operations');
  });

  // Test Case 8: Refreshing customer dashboard does not redirect to mechanic portal
  it('8. ensures refreshing on customer dashboard retains customer portal', () => {
    const customerUser = { role: 'customer' as UserRole };
    const routeCheck = resolveRoleRoute('/customer/dashboard', customerUser, ['customer', 'admin']);
    expect(routeCheck.allowed).toBe(true);
    expect(routeCheck.redirectPath).toBeNull();

    // Even if previous state.from was /mechanic/dashboard, customer redirect sanitizes it
    const sanitized = resolveLoginRedirect('/mechanic/dashboard', customerUser.role);
    expect(sanitized).toBe('/customer/dashboard');
  });

  // Test Case 9: Refreshing mechanic dashboard does not redirect to customer portal
  it('9. ensures refreshing on mechanic dashboard retains mechanic portal', () => {
    const mechanicUser = { role: 'mechanic' as UserRole };
    const routeCheck = resolveRoleRoute('/mechanic/dashboard', mechanicUser, ['mechanic']);
    expect(routeCheck.allowed).toBe(true);
    expect(routeCheck.redirectPath).toBeNull();

    // Even if previous state.from was /customer/dashboard, mechanic redirect sanitizes it
    const sanitized = resolveLoginRedirect('/customer/dashboard', mechanicUser.role);
    expect(sanitized).toBe('/mechanic/dashboard');
  });
});
