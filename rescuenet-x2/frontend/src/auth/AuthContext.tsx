import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api, refreshSession, tokenStore, UNAUTHORIZED_EVENT } from '../api/client';
import type { AuthUser, PortalId, RegisterPayload } from '../api/types';
import { toast } from '../lib/toast';

interface AuthState {
  user: AuthUser | null;
  /** True while the saved session is being checked on page load. */
  restoring: boolean;
  /** Either a signed-in user, or a challenge: the account has MFA and still owes a code (no session exists yet). */
  login: (portal: PortalId, username: string, password: string, remember: boolean) => Promise<{ user: AuthUser } | { challenge: string; expiresIn: number }>;
  completeMfa: (challenge: string, input: { code?: string; recovery_code?: string }) => Promise<AuthUser>;
  register: (payload: RegisterPayload, remember: boolean) => Promise<AuthUser>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  // Always true on first load: the session is restored from the HttpOnly refresh cookie, not from browser storage.
  const [restoring, setRestoring] = useState<boolean>(true);
  const timer = useRef<number | undefined>(undefined);

  const clearTimer = () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = undefined;
  };

  // Renew the access token shortly before it expires so people are never interrupted.
  const scheduleRefresh = useCallback((expiresInSeconds: number) => {
    clearTimer();
    timer.current = window.setTimeout(async () => {
      const renewed = await refreshSession();
      if (renewed) scheduleRefresh(renewed.expires_in);
      else if (tokenStore.get() === null) window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
      else scheduleRefresh(60); // network problem: try again in a minute
    }, Math.max(15, expiresInSeconds * 0.8) * 1000);
  }, []);

  const endLocalSession = useCallback(() => {
    clearTimer();
    tokenStore.clear();
    setUser(null);
  }, []);

  const logout = useCallback(() => {
    api.logout().catch(() => undefined).finally(endLocalSession);
  }, [endLocalSession]);

  // Restore a session after a page load or reload.
  useEffect(() => {
    let cancelled = false;
    refreshSession()
      .then((res) => {
        if (cancelled || !res) return;
        setUser(res.user);
        scheduleRefresh(res.expires_in);
      })
      .finally(() => !cancelled && setRestoring(false));
    return () => {
      cancelled = true;
      clearTimer();
    };
  }, [scheduleRefresh]);

  // The API refused us and a refresh did not help: the session was ended (expired, signed out elsewhere, role or password
  // changed, account disabled).
  useEffect(() => {
    const onUnauthorized = () => {
      if (!tokenStore.get() && !user) return;
      endLocalSession();
      toast.info('Your session ended. Please sign in again.');
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, [endLocalSession, user]);

  const adopt = (res: { access_token: string; csrf_token: string; expires_in: number; user: AuthUser }) => {
    tokenStore.set(res.access_token, res.csrf_token);
    setUser(res.user);
    scheduleRefresh(res.expires_in);
    return res.user;
  };

  const login: AuthState['login'] = async (portal, username, password, remember) => {
    const res = await api.login(portal, username.trim(), password, remember);
    if (res.status === 'mfa_required') return { challenge: res.challenge_token, expiresIn: res.expires_in };
    return { user: adopt(res) };
  };

  const completeMfa: AuthState['completeMfa'] = async (challenge, input) => adopt(await api.mfaVerify(challenge, input));

  const register: AuthState['register'] = async (payload) => adopt(await api.register(payload));

  const refreshUser = async () => {
    try {
      setUser(await api.getMe());
    } catch {
      /* a 401 is handled by the listener above */
    }
  };

  return <Ctx.Provider value={{ user, restoring, login, completeMfa, register, logout, refreshUser }}>{children}</Ctx.Provider>;
};

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>');
  return v;
}
