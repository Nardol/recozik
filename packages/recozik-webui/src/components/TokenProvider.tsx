"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { fetchWhoami, WhoAmI } from "../lib/api";

interface TokenContextValue {
  token: string | null;
  profile: WhoAmI | null;
  status: "idle" | "loading" | "error";
  setToken: (value: string) => void;
  clearToken: () => void;
  refreshProfile: () => Promise<void>;
}

const TokenContext = createContext<TokenContextValue | undefined>(undefined);

const STORAGE_KEY = "recozik-webui-token";

interface Props {
  children: React.ReactNode;
  initialToken?: string | null;
  initialProfile?: WhoAmI | null;
}

export function TokenProvider({
  children,
  initialToken = null,
  initialProfile = null,
}: Props) {
  const [token, setTokenState] = useState<string | null>(initialToken);
  const [profile, setProfile] = useState<WhoAmI | null>(initialProfile);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");

  const persistToken = useCallback((value: string | null) => {
    if (typeof window === "undefined") return;
    if (value) {
      window.localStorage.setItem(STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    if (initialToken) {
      persistToken(initialToken);
      return;
    }
    const saved =
      typeof window !== "undefined"
        ? window.localStorage.getItem(STORAGE_KEY)
        : null;
    if (saved) {
      setTokenState(saved);
    }
  }, [initialToken, persistToken]);

  const setToken = useCallback(
    (value: string) => {
      setTokenState(value);
      persistToken(value);
    },
    [persistToken],
  );

  const clearToken = useCallback(() => {
    setTokenState(null);
    setProfile(null);
    setStatus("idle");
    persistToken(null);
  }, [persistToken]);

  const refreshProfile = useCallback(async () => {
    if (!token) return;
    try {
      setStatus("loading");
      const data = await fetchWhoami(token);
      setProfile(data);
      setStatus("idle");
    } catch (error) {
      console.error("Unable to load profile", error);
      setStatus("error");
      setProfile(null);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      refreshProfile();
    } else {
      setProfile(null);
      setStatus("idle");
    }
  }, [token, refreshProfile]);

  const value = useMemo(
    () => ({ token, profile, status, setToken, clearToken, refreshProfile }),
    [token, profile, status, setToken, clearToken, refreshProfile],
  );

  return (
    <TokenContext.Provider value={value}>{children}</TokenContext.Provider>
  );
}

export function useToken() {
  const ctx = useContext(TokenContext);
  if (!ctx) {
    throw new Error("useToken must be used within TokenProvider");
  }
  return ctx;
}
