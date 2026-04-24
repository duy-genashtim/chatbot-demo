/**
 * NextAuth (Auth.js v5 beta) configuration for Microsoft Entra ID.
 *
 * Exports handlers, signIn, signOut, auth — the four canonical exports
 * required by Auth.js v5 App Router integration.
 *
 * The idToken is persisted in the JWT/session so the frontend can attach
 * it as a Bearer token on requests to the FastAPI backend.
 *
 * Environment variables (server-side only — not NEXT_PUBLIC_):
 *   AZURE_AD_TENANT_ID      — Entra tenant GUID (used to build issuer URL)
 *   AZURE_AD_CLIENT_ID      — app registration client ID
 *   AZURE_AD_CLIENT_SECRET  — app registration client secret
 *   NEXTAUTH_SECRET         — 32+ byte random string for JWT encryption
 */

import NextAuth from "next-auth";
import MicrosoftEntraId from "next-auth/providers/microsoft-entra-id";
import type { Account, Session } from "next-auth";
import type { JWT } from "next-auth/jwt";

/**
 * Build tenant-specific issuer URL. Microsoft's OIDC discovery document
 * returns the issuer WITHOUT a trailing slash — oauth4webapi compares
 * strings exactly, so we must match that form or signIn fails with
 * OperationProcessingError: "issuer" does not match.
 */
function buildIssuer(): string {
  const tenantId = process.env.AZURE_AD_TENANT_ID;
  if (!tenantId) return "https://login.microsoftonline.com/common/v2.0";
  return `https://login.microsoftonline.com/${tenantId}/v2.0`;
}

/** Extend JWT to carry the Entra id_token and admin flag through to the session. */
interface EntraJWT extends JWT {
  idToken?: string;
  refreshToken?: string;
  /** Epoch seconds at which the id_token expires. */
  expiresAt?: number;
  is_admin?: boolean;
  /** Set when refresh fails — forces client to sign out. */
  error?: "RefreshAccessTokenError";
}

/** Extend Session to expose the id_token and admin flag to calling code. */
export interface EntraSession extends Session {
  idToken?: string;
  error?: "RefreshAccessTokenError";
  user: Session["user"] & { is_admin?: boolean };
}

/**
 * Refresh the Entra id_token using the stored refresh_token.
 * Returns an updated JWT (new idToken + expiresAt) or one flagged with
 * `error: "RefreshAccessTokenError"` so the session callback can surface it.
 */
async function refreshIdToken(token: EntraJWT): Promise<EntraJWT> {
  try {
    const tenantId = process.env.AZURE_AD_TENANT_ID ?? "common";
    const url = `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`;
    const body = new URLSearchParams({
      client_id: process.env.AZURE_AD_CLIENT_ID ?? "",
      client_secret: process.env.AZURE_AD_CLIENT_SECRET ?? "",
      grant_type: "refresh_token",
      refresh_token: token.refreshToken ?? "",
      scope: "openid email profile offline_access",
    });
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const data = (await resp.json()) as {
      id_token?: string;
      refresh_token?: string;
      expires_in?: number;
      error?: string;
    };
    if (!resp.ok || !data.id_token) {
      throw new Error(data.error ?? "refresh_failed");
    }
    return {
      ...token,
      idToken: data.id_token,
      refreshToken: data.refresh_token ?? token.refreshToken,
      expiresAt: Math.floor(Date.now() / 1000) + (data.expires_in ?? 3600),
      error: undefined,
    };
  } catch {
    return { ...token, error: "RefreshAccessTokenError" };
  }
}

export const { handlers, signIn, signOut, auth } = NextAuth({
  // Allow localhost redirects in dev without hardcoding NEXTAUTH_URL.
  trustHost: true,

  // Auth.js v5 reads AUTH_SECRET by default; accept legacy NEXTAUTH_SECRET too.
  secret: process.env.AUTH_SECRET ?? process.env.NEXTAUTH_SECRET,

  providers: [
    MicrosoftEntraId({
      clientId: process.env.AZURE_AD_CLIENT_ID ?? "",
      clientSecret: process.env.AZURE_AD_CLIENT_SECRET ?? "",
      issuer: buildIssuer(),
      authorization: {
        params: { scope: "openid email profile offline_access" },
      },
    }),
  ],

  callbacks: {
    /**
     * On sign-in, capture the id_token from the OAuth account object,
     * fetch is_admin from the backend, and store both in the encrypted JWT
     * cookie. On subsequent calls the JWT is already populated — pass through.
     */
    async jwt({
      token,
      account,
    }: {
      token: JWT;
      account?: Account | null;
    }): Promise<JWT> {
      const entraToken = token as EntraJWT;
      if (account?.id_token) {
        entraToken.idToken = account.id_token;
        entraToken.refreshToken = account.refresh_token as string | undefined;
        entraToken.expiresAt =
          (account.expires_at as number | undefined) ??
          (Math.floor(Date.now() / 1000) + 3600);
        // Fetch admin flag from backend on first sign-in
        try {
          const apiBase =
            process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
            "http://localhost:8000/api";
          const resp = await fetch(`${apiBase}/auth/me`, {
            headers: { Authorization: `Bearer ${account.id_token}` },
          });
          if (resp.ok) {
            const me = (await resp.json()) as { is_admin?: boolean };
            entraToken.is_admin = me.is_admin ?? false;
          }
        } catch {
          entraToken.is_admin = false;
        }
        return entraToken;
      }

      // Subsequent calls: refresh id_token 60s before it expires
      const now = Math.floor(Date.now() / 1000);
      if (
        entraToken.expiresAt &&
        entraToken.refreshToken &&
        now >= entraToken.expiresAt - 60
      ) {
        return refreshIdToken(entraToken);
      }
      return entraToken;
    },

    /**
     * Expose the idToken and is_admin on the Session object so both client
     * components (useSession()) and server components (auth()) can read them.
     */
    async session({
      session,
      token,
    }: {
      session: Session;
      token: JWT;
    }): Promise<EntraSession> {
      const entraToken = token as EntraJWT;
      return {
        ...session,
        idToken: entraToken.idToken,
        error: entraToken.error,
        user: {
          ...session.user,
          is_admin: entraToken.is_admin ?? false,
        },
      };
    },
  },

  // Encrypted JWT session cookie — never stored in localStorage.
  // Secure flag applied automatically by NextAuth when URL is https://.
  session: {
    strategy: "jwt",
    // 8h session; id_token auto-refreshes via refresh_token within this window.
    maxAge: 60 * 60 * 8,
  },
});
