"use client";

/**
 * SessionProvider wrapper — must be a client component so that
 * next-auth/react's React context is available throughout the tree.
 *
 * Import this in the root layout (server component) to wrap children
 * without losing server-component benefits on the rest of the tree.
 */

import { SessionProvider as NextAuthSessionProvider } from "next-auth/react";
import type { Session } from "next-auth";

interface Props {
  children: React.ReactNode;
  /** Optional: pass a server-fetched session to avoid client waterfall. */
  session?: Session | null;
}

export function SessionProvider({ children, session }: Props) {
  return (
    <NextAuthSessionProvider session={session}>
      {children}
    </NextAuthSessionProvider>
  );
}
