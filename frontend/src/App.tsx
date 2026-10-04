import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { CustomerDashboardPage } from './pages/CustomerDashboardPage';
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

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();
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

  return <>{children}</>;
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
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <CustomerDashboardPage />
                </ProtectedRoute>
              }
            />
            <Route path="/bookings" element={<Navigate to="/dashboard" replace />} />
            <Route
              path="/bookings/:bookingId"
              element={
                <ProtectedRoute>
                  <BookingDetailsPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bookings/:bookingId/tracking"
              element={
                <ProtectedRoute>
                  <BookingTrackingPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bookings/:bookingId/chat"
              element={
                <ProtectedRoute>
                  <BookingChatPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bookings/:bookingId/review"
              element={
                <ProtectedRoute>
                  <BookingReviewPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Mechanic Dashboard Route */}
            <Route
              path="/mechanic/dashboard"
              element={
                <ProtectedRoute>
                  <MechanicDashboardPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Mechanic Payouts Route (Phase 8.7) */}
            <Route
              path="/mechanic/payouts"
              element={
                <ProtectedRoute>
                  <MechanicPayoutsPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Mechanic Banking & Payout Account Route (Phase 8.8) */}
            <Route
              path="/mechanic/payout-account"
              element={
                <ProtectedRoute>
                  <MechanicPayoutAccountPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Settlement Management Route (Phase 8.9) */}
            <Route
              path="/admin/settlements"
              element={
                <ProtectedRoute>
                  <SettlementManagementPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Operations & Observability Dashboard (Phase 9) */}
            <Route
              path="/admin/operations"
              element={
                <ProtectedRoute>
                  <OperationsDashboardPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Audit Log Viewer (Phase 9) */}
            <Route
              path="/admin/audit-logs"
              element={
                <ProtectedRoute>
                  <AuditLogPage />
                </ProtectedRoute>
              }
            />

            {/* Protected Admin Intelligent Matching & Dispatch Operations (Phase 11) */}
            <Route
              path="/admin/matching"
              element={
                <ProtectedRoute>
                  <MatchingDashboardPage />
                </ProtectedRoute>
              }
            />

            {/* Root redirect */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </main>
      </div>
    </ErrorBoundary>
  );
};

export default App;
