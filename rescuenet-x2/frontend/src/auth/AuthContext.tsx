import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, tokenStore, UNAUTHORIZED_EVENT } from '../api/client';
import type { AuthUser, PortalId, RegisterPayload } from '../api/types';
import { toast } from '../lib/toast';

interface AuthState {
  user: AuthUser | null;
  /** True while the saved session is being checked on page load. */
  restoring: boolean;
  login: (portal: PortalId, username: string, password: string, remember: boolean) => Promise<AuthUser>;
  register: (payload: RegisterPayload, remember: boolean) => Promise<AuthUser>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [restoring, setRestoring] = useState<boolean>(() => !!tokenStore.get());

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  // Restore a saved session.
  useEffect(() => {
    if (!tokenStore.get()) return;
    api
      .getMe()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setRestoring(false));
  }, []);

  // Any 401 from the API means the token expired or the account was disabled.
  useEffect(() => {
    const onUnauthorized = () => {
      if (!tokenStore.get()) return;
      logout();
      toast.info('Your session ended. Please sign in again.');
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [logout]);

  const login: AuthState['login'] = async (portal, username, password, remember) => {
    const res = await api.login(portal, username.trim(), password);
    tokenStore.set(res.access_token, remember);
    setUser(res.user);
    return res.user;
  };

  const register: AuthState['register'] = async (payload, remember) => {
    const res = await api.register(payload);
    tokenStore.set(res.access_token, remember);
    setUser(res.user);
    return res.user;
  };

  const refreshUser = async () => {
    try {
      setUser(await api.getMe());
    } catch {
      /* a 401 is handled by the listener above */
    }
  };

  return <Ctx.Provider value={{ user, restoring, login, register, logout, refreshUser }}>{children}</Ctx.Provider>;
};

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>');
  return v;
}
