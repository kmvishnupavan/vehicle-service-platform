import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { CustomerDashboardPage } from './pages/CustomerDashboardPage';
import { BookServicePage } from './pages/BookServicePage';
import { BookingDetailsPage } from './pages/BookingDetailsPage';
import { BookingTrackingPage } from './pages/BookingTrackingPage';
import { BookingChatPage } from './pages/BookingChatPage';
import { BookingReviewPage } from './pages/BookingReviewPage';
import { MechanicDashboardPage } from './pages/MechanicDashboardPage';
import { MechanicPayoutsPage } from './pages/MechanicPayoutsPage';
import { MechanicPayoutAccountPage } from './pages/MechanicPayoutAccountPage';
import { SettlementManagementPage } from './pages/admin/SettlementManagementPage';
import { OperationsDashboardPage } from './pages/admin/OperationsDashboardPage';
import { AuditLogPage } from './pages/admin/AuditLogPage';
import { MatchingDashboardPage } from './pages/admin/MatchingDashboardPage';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { useAuth } from './context/AuthContext';
import { UserRole, getDefaultDashboardForRole } from './types/user';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, allowedRoles }) => {
  const { user, role, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Enforce role-based access control
  if (allowedRoles && role && !allowedRoles.includes(role)) {
    return <Navigate to={getDefaultDashboardForRole(role)} replace />;
  }

  return <>{children}</>;
};

export const RoleHomeRedirect: React.FC = () => {
  const { user, role, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={getDefaultDashboardForRole(role)} replace />;
};

export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
        <Navbar />
        <main className="flex-1">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            {/* Protected Customer Routes */}
            <Route
              path="/customer/dashboard"
              element={
                <ProtectedRoute allowedRoles={['customer', 'admin']}>
                  <CustomerDashboardPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/customer/book-service"
              element={
                <ProtectedRoute allowedRoles={['customer', 'admin']}>
                  <BookServicePage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/book-service"
              element={<Navigate to="/customer/book-service" replace />}
            />
            {/* Alias /dashboard -> /customer/dashboard */}
            <Route
              path="/dashboard"
              element={<Navigate to="/customer/dashboard" replace />}
            />
            <Route
              path="/bookings"
              element={<Navigate to="/customer/dashboard" replace />}
            />
            <Route
              path="/bookings/:bookingId"
              element={
                <ProtectedRoute allowedRoles={['customer', 'admin']}>
                  <BookingDetailsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bookings/:bookingId/tracking"
              element={
                <ProtectedRoute allowedRoles={['customer', 'admin']}>
                  <BookingTrackingPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bookings/:bookingId/chat"
              element={
                <ProtectedRoute allowedRoles={['customer', 'mechanic', 'admin', 'support']}>
                  <BookingChatPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bookings/:bookingId/review"
              element={
                <ProtectedRoute allowedRoles={['customer', 'admin']}>
                  <BookingReviewPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Mechanic Dashboard Route */}
            <Route
              path="/mechanic/dashboard"
              element={
                <ProtectedRoute allowedRoles={['mechanic', 'admin']}>
                  <MechanicDashboardPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Mechanic Payouts Route (Phase 8.7) */}
            <Route
              path="/mechanic/payouts"
              element={
                <ProtectedRoute allowedRoles={['mechanic', 'admin']}>
                  <MechanicPayoutsPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Mechanic Banking & Payout Account Route (Phase 8.8) */}
            <Route
              path="/mechanic/payout-account"
              element={
                <ProtectedRoute allowedRoles={['mechanic', 'admin']}>
                  <MechanicPayoutAccountPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Settlement Management Route (Phase 8.9) */}
            <Route
              path="/admin/settlements"
              element={
                <ProtectedRoute allowedRoles={['admin', 'support']}>
                  <SettlementManagementPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Operations & Observability Dashboard (Phase 9) */}
            <Route
              path="/admin/operations"
              element={
                <ProtectedRoute allowedRoles={['admin', 'support']}>
                  <OperationsDashboardPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Audit Log Viewer (Phase 9) */}
            <Route
              path="/admin/audit-logs"
              element={
                <ProtectedRoute allowedRoles={['admin', 'support']}>
                  <AuditLogPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Intelligent Matching & Dispatch Operations (Phase 11) */}
            <Route
              path="/admin/matching"
              element={
                <ProtectedRoute allowedRoles={['admin', 'support']}>
                  <MatchingDashboardPage />
                </ProtectedRoute>
              }
            />

            {/* Role-Aware Root & Fallback Redirects */}
            <Route path="/" element={<RoleHomeRedirect />} />
            <Route path="*" element={<RoleHomeRedirect />} />
          </Routes>
        </main>
      </div>
    </ErrorBoundary>
  );
};

export default App;
