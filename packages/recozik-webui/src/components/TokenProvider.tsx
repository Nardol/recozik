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
  refreshProfile: () => Promise<void>;
}

const TokenContext = createContext<TokenContextValue | undefined>(undefined);

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
  const [status, setStatus] = useState<"idle" | "loading" | "error">(
    initialProfile ? "idle" : "loading",
  );

  const refreshProfile = useCallback(async () => {
    try {
      setStatus("loading");
      const data = await fetchWhoami();
      setProfile(data);
      setStatus("idle");
      setTokenState("session");
    } catch (error) {
      console.error("Unable to load profile", error);
      setStatus("error");
      setProfile(null);
      setTokenState(null);
    }
  }, []);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  const value = useMemo(
    () => ({ token, profile, status, refreshProfile }),
    [token, profile, status, refreshProfile],
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
