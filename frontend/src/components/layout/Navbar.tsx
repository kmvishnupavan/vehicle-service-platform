import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Wrench, User as UserIcon, LogOut, Calendar, MessageSquare, Wallet, ShieldCheck, Activity, FileText } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useUnreadChatCount } from '../../hooks/useChat';

export const Navbar: React.FC = () => {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { data: unreadData } = useUnreadChatCount();

  const unreadCount = unreadData?.unread_count || 0;

  const handleSignOut = async () => {
    await signOut();
    navigate('/login');
  };

  return (
    <nav className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center space-x-8">
            <Link to="/dashboard" className="flex items-center space-x-2 text-slate-900 font-bold text-lg tracking-tight">
              <div className="bg-emerald-600 p-2 rounded-lg text-white">
                <Wrench className="w-5 h-5" />
              </div>
              <span>VehicleCare</span>
            </Link>
            {user && (
              <div className="hidden sm:flex sm:space-x-4 items-center">
                <Link
                  to="/dashboard"
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition"
                >
                  <Calendar className="w-4 h-4 mr-1.5" />
                  My Bookings
                </Link>

                <Link
                  to="/mechanic/dashboard"
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition"
                >
                  <Wrench className="w-4 h-4 mr-1.5" />
                  Mechanic Portal
                </Link>

                <Link
                  to="/mechanic/payouts"
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition"
                >
                  <Wallet className="w-4 h-4 mr-1.5" />
                  Payouts
                </Link>

                <Link
                  to="/admin/settlements"
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition"
                >
                  <ShieldCheck className="w-4 h-4 mr-1.5" />
                  Settlements
                </Link>

                <Link
                  to="/admin/operations"
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition"
                >
                  <Activity className="w-4 h-4 mr-1.5" />
                  Operations
                </Link>

                <Link
                  to="/admin/audit-logs"
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium text-slate-700 hover:text-emerald-600 hover:bg-slate-50 transition"
                >
                  <FileText className="w-4 h-4 mr-1.5" />
                  Audit Logs
                </Link>

                {unreadCount > 0 && (
                  <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 animate-pulse">
                    <MessageSquare className="w-3 h-3" />
                    <span>{unreadCount} unread</span>
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center space-x-4">
            {user ? (
              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2 text-sm text-slate-600">
                  <UserIcon className="w-4 h-4 text-slate-400" />
                  <span className="hidden md:inline font-medium">{user.email}</span>
                </div>
                <button
                  onClick={handleSignOut}
                  className="inline-flex items-center px-3 py-1.5 rounded-md text-sm font-medium text-slate-700 hover:text-red-600 hover:bg-red-50 border border-slate-200 transition"
                  title="Sign Out"
                >
                  <LogOut className="w-4 h-4 sm:mr-1.5" />
                  <span className="hidden sm:inline">Sign Out</span>
                </button>
              </div>
            ) : (
              <div className="flex items-center space-x-2">
                <Link
                  to="/login"
                  className="px-4 py-2 rounded-lg text-sm font-medium text-slate-700 hover:text-slate-900 transition"
                >
                  Sign In
                </Link>
                <Link
                  to="/register"
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm transition"
                >
                  Register
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
};
