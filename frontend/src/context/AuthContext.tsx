/**
 * Authentication Context and Provider.
 *
 * Wraps Supabase Auth for reactive session lifecycle, login, registration, and logout.
 * Authoritatively retrieves and exposes user database profile and role.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { Session, User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import { UserProfile, UserRole } from '../types/user';

interface SignInResult {
  error: Error | null;
  role?: UserRole;
  profile?: UserProfile | null;
}

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: UserProfile | null;
  role: UserRole | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<SignInResult>;
  signUp: (email: string, password: string, fullName?: string, requestedRole?: UserRole) => Promise<{ error: Error | null }>;
  signOut: () => Promise<void>;
  refreshProfile: () => Promise<UserProfile | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchProfile = useCallback(async (authUser: User | null): Promise<UserProfile | null> => {
    if (!authUser) {
      setProfile(null);
      setRole(null);
      return null;
    }

    try {
      // 1. Direct query to public.profiles via Supabase client (respects RLS profiles_select_policy)
      const { data, error } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', authUser.id)
        .maybeSingle();

      if (!error && data) {
        const userProfile = data as UserProfile;
        setProfile(userProfile);
        setRole(userProfile.role || 'customer');
        return userProfile;
      }
    } catch {
      // Ignore database fetch error, proceed to fallback
    }

    // 2. Fallback to auth user metadata or default customer
    const metaRole = (authUser.user_metadata?.role as UserRole) || 'customer';
    const fallbackProfile: UserProfile = {
      id: authUser.id,
      full_name: authUser.user_metadata?.full_name || authUser.email?.split('@')[0] || 'User',
      email: authUser.email,
      role: metaRole,
      is_active: true,
    };
    setProfile(fallbackProfile);
    setRole(metaRole);
    return fallbackProfile;
  }, []);

  const refreshProfile = useCallback(async () => {
    return await fetchProfile(user);
  }, [fetchProfile, user]);

  useEffect(() => {
    let isMounted = true;

    // Initial session retrieval
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!isMounted) return;
      setSession(session);
      setUser(session?.user ?? null);
      if (session?.user) {
        await fetchProfile(session.user);
      } else {
        setProfile(null);
        setRole(null);
      }
      setLoading(false);
    });

    // Listen for auth state changes (login, logout, token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
      if (!isMounted) return;
      setSession(session);
      setUser(session?.user ?? null);
      if (session?.user) {
        await fetchProfile(session.user);
      } else {
        setProfile(null);
        setRole(null);
      }
      setLoading(false);
    });

    return () => {
      isMounted = false;
      subscription.unsubscribe();
    };
  }, [fetchProfile]);

  const signIn = async (email: string, password: string): Promise<SignInResult> => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) {
      return { error: new Error(error.message) };
    }
    let userProfile: UserProfile | null = null;
    if (data.user) {
      userProfile = await fetchProfile(data.user);
    }
    return {
      error: null,
      role: userProfile?.role || 'customer',
      profile: userProfile,
    };
  };

  const signUp = async (
    email: string,
    password: string,
    fullName?: string,
    requestedRole: UserRole = 'customer'
  ) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName || email.split('@')[0],
          role: requestedRole,
        },
      },
    });
    return { error: error ? new Error(error.message) : null };
  };

  const signOut = async () => {
    await supabase.auth.signOut();
    setUser(null);
    setSession(null);
    setProfile(null);
    setRole(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        profile,
        role,
        loading,
        signIn,
        signUp,
        signOut,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
