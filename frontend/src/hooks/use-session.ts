"use client";

/**
 * Thin wrapper around next-auth/react useSession.
 * Exposes { session, idToken, isAdmin, status } so callers
 * don't need to know the EntraSession shape.
 *
 * If refresh_token flow fails (session.error === "RefreshAccessTokenError"),
 * auto-signs the user out and returns them to "/".
 */

import { useEffect } from "react";
import { useSession as useNextAuthSession, signOut } from "next-auth/react";
import type { EntraSession } from "@/lib/auth-config";

export interface UseSessionResult {
  session: EntraSession | null;
  idToken: string | null;
  isAdmin: boolean;
  status: "loading" | "authenticated" | "unauthenticated";
}

export function useSession(): UseSessionResult {
  const { data, status } = useNextAuthSession();
  const session = data as EntraSession | null;

  useEffect(() => {
    if (session?.error === "RefreshAccessTokenError") {
      void signOut({ callbackUrl: "/" });
    }
  }, [session?.error]);

  return {
    session,
    idToken: session?.idToken ?? null,
    isAdmin: session?.user?.is_admin === true,
    status,
  };
}
