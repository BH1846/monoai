import React, { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from 'react';

export interface GatewayConfig {
  gatewayUrl: string;
  adminKey: string;
  virtualKey: string;
  adminEmail: string;
}

const SESSION_STORAGE_KEYS = {
  adminKey: 'monoai_admin_key',
  virtualKey: 'monoai_virtual_key',
} as const;

// Not secrets -- safe to survive a browser restart (unlike adminKey/virtualKey
// above, which stay session-scoped in-browser; the admin key's actual
// cross-session persistence is server-side, see loadAdminKeyForEmail below).
const LOCAL_STORAGE_KEYS = {
  gatewayUrl: 'monoai_gateway_url',
  adminEmail: 'monoai_admin_email',
} as const;

export const DEFAULT_GATEWAY_URL = 'http://localhost:8000';

function readSession(key: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return sessionStorage.getItem(key) ?? fallback;
}

function readLocal(key: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return localStorage.getItem(key) ?? fallback;
}

interface GatewayContextValue {
  config: GatewayConfig;
  setGatewayUrl: (val: string) => void;
  setAdminKey: (val: string) => void;
  setVirtualKey: (val: string) => void;
  setAdminEmail: (val: string) => void;
  // Calls /api/admin/<pathSuffix> on our own Express server, which injects
  // the admin bearer + target gateway URL server-side. Never hits the
  // gateway directly from the browser.
  adminFetch: (pathSuffix: string, init?: RequestInit) => Promise<Response>;
  // Headers to attach to /api/chat requests so the proxy knows which
  // virtual key + gateway to use for this session.
  chatHeaders: () => Record<string, string>;
  // Server-side "remember this admin key for this email" pair (gateway/auth/
  // admin_account_store.py) so the console only has to be handed the admin
  // key once per deployment, not once per browser session.
  loadAdminKeyForEmail: (email: string) => Promise<string | null>;
  saveAdminKeyForEmail: (email: string, key: string) => Promise<boolean>;
  // Current virtual key's model_allowlist (via GET /v1/me), refreshed
  // whenever virtualKey/gatewayUrl changes. `null` means "unrestricted or
  // not yet known" -- callers should treat null as "show everything," not
  // "show nothing."
  modelAllowlist: string[] | null;
}

const GatewayContext = createContext<GatewayContextValue | undefined>(undefined);

export function GatewayProvider({ children }: { children: ReactNode }) {
  const [gatewayUrl, setGatewayUrlState] = useState(() => readLocal(LOCAL_STORAGE_KEYS.gatewayUrl, DEFAULT_GATEWAY_URL));
  const [adminKey, setAdminKeyState] = useState(() => readSession(SESSION_STORAGE_KEYS.adminKey, ''));
  const [virtualKey, setVirtualKeyState] = useState(() => readSession(SESSION_STORAGE_KEYS.virtualKey, ''));
  const [adminEmail, setAdminEmailState] = useState(() => readLocal(LOCAL_STORAGE_KEYS.adminEmail, ''));
  const [modelAllowlist, setModelAllowlist] = useState<string[] | null>(null);

  const setGatewayUrl = useCallback((val: string) => {
    setGatewayUrlState(val);
    localStorage.setItem(LOCAL_STORAGE_KEYS.gatewayUrl, val);
  }, []);

  const setAdminKey = useCallback((val: string) => {
    setAdminKeyState(val);
    sessionStorage.setItem(SESSION_STORAGE_KEYS.adminKey, val);
  }, []);

  const setVirtualKey = useCallback((val: string) => {
    setVirtualKeyState(val);
    sessionStorage.setItem(SESSION_STORAGE_KEYS.virtualKey, val);
  }, []);

  const setAdminEmail = useCallback((val: string) => {
    setAdminEmailState(val);
    localStorage.setItem(LOCAL_STORAGE_KEYS.adminEmail, val);
  }, []);

  const adminFetch = useCallback(
    (pathSuffix: string, init: RequestInit = {}) => {
      const headers = new Headers(init.headers || {});
      headers.set('x-monoai-admin-key', adminKey);
      headers.set('x-monoai-gateway-url', gatewayUrl);
      if (init.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }
      return fetch(`/api/admin/${pathSuffix}`, { ...init, headers });
    },
    [adminKey, gatewayUrl]
  );

  const chatHeaders = useCallback(
    () => ({
      'x-monoai-virtual-key': virtualKey,
      'x-monoai-gateway-url': gatewayUrl,
    }),
    [virtualKey, gatewayUrl]
  );

  // Deliberately doesn't go through adminFetch -- these two calls run
  // *before* adminKey is necessarily set in state (loadAdminKeyForEmail is
  // how it gets set in the first place), so they build headers explicitly.
  const loadAdminKeyForEmail = useCallback(
    async (email: string): Promise<string | null> => {
      try {
        const res = await fetch(`/api/admin/account/${encodeURIComponent(email.trim().toLowerCase())}`, {
          headers: { 'x-monoai-gateway-url': gatewayUrl },
        });
        if (!res.ok) return null;
        const data = await res.json();
        return data.admin_key ?? null;
      } catch {
        return null;
      }
    },
    [gatewayUrl]
  );

  const saveAdminKeyForEmail = useCallback(
    async (email: string, key: string): Promise<boolean> => {
      try {
        const res = await fetch('/api/admin/account', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-monoai-admin-key': key,
            'x-monoai-gateway-url': gatewayUrl,
          },
          body: JSON.stringify({ email: email.trim().toLowerCase() }),
        });
        return res.ok;
      } catch {
        return false;
      }
    },
    [gatewayUrl]
  );

  useEffect(() => {
    let cancelled = false;
    if (!virtualKey) {
      setModelAllowlist(null);
      return;
    }
    fetch('/api/me', { headers: chatHeaders() })
      .then(async (res) => {
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (cancelled) return;
        setModelAllowlist(Array.isArray(data.model_allowlist) ? data.model_allowlist : null);
      })
      .catch(() => {
        if (!cancelled) setModelAllowlist(null);
      });
    return () => {
      cancelled = true;
    };
  }, [virtualKey, gatewayUrl, chatHeaders]);

  const value = useMemo<GatewayContextValue>(
    () => ({
      config: { gatewayUrl, adminKey, virtualKey, adminEmail },
      setGatewayUrl,
      setAdminKey,
      setVirtualKey,
      setAdminEmail,
      adminFetch,
      chatHeaders,
      loadAdminKeyForEmail,
      saveAdminKeyForEmail,
      modelAllowlist,
    }),
    [
      gatewayUrl, adminKey, virtualKey, adminEmail,
      setGatewayUrl, setAdminKey, setVirtualKey, setAdminEmail,
      adminFetch, chatHeaders, loadAdminKeyForEmail, saveAdminKeyForEmail,
      modelAllowlist,
    ]
  );

  return <GatewayContext.Provider value={value}>{children}</GatewayContext.Provider>;
}

export function useGateway(): GatewayContextValue {
  const ctx = useContext(GatewayContext);
  if (!ctx) throw new Error('useGateway must be used within a GatewayProvider');
  return ctx;
}
