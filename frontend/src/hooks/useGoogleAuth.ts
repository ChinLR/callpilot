import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";

const USER_ID_KEY = "callpilot_user_id";
const GOOGLE_CONNECTED_KEY = "callpilot_google_connected";

function getOrCreateUserId(): string {
  let id = localStorage.getItem(USER_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(USER_ID_KEY, id);
  }
  return id;
}

export function useGoogleAuth() {
  const [isConnected, setIsConnected] = useState(() =>
    localStorage.getItem(GOOGLE_CONNECTED_KEY) === "true"
  );
  const [isLoading, setIsLoading] = useState(false);

  const [oauthError, setOauthError] = useState<string | null>(null);
  const [justConnected, setJustConnected] = useState(false);

  // Check for ?oauth=success or ?oauth=error on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauthParam = params.get("oauth");

    if (oauthParam === "success") {
      setIsConnected(true);
      setJustConnected(true);
      localStorage.setItem(GOOGLE_CONNECTED_KEY, "true");
    } else if (oauthParam === "error") {
      const detail = params.get("detail") || "Google sign-in failed";
      setOauthError(detail);
    }

    if (oauthParam) {
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);

  const connect = useCallback(async () => {
    setIsLoading(true);
    try {
      const userId = getOrCreateUserId();
      const { authorize_url } = await api.googleAuthorize(userId);
      window.location.href = authorize_url;
    } catch (err) {
      setIsLoading(false);
      throw err;
    }
  }, []);

  const disconnect = useCallback(() => {
    localStorage.removeItem(GOOGLE_CONNECTED_KEY);
    setIsConnected(false);
  }, []);

  const userId = getOrCreateUserId();

  return { isConnected, isLoading, connect, disconnect, userId, oauthError, clearOauthError: () => setOauthError(null), justConnected };
}
