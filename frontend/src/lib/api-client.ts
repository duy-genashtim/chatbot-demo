/**
 * Fetch wrapper for chatbotv2 frontend.
 *
 * Public helpers (api.get/post/put/delete) — for anonymous/public routes.
 * Authenticated helper (fetchWithAuth) — attaches Bearer token for
 *   /api/internal/* and /api/admin/* routes. Caller passes the idToken
 *   obtained from useSession().idToken or auth().idToken.
 *
 * Usage (public):
 *   import { api } from "@/lib/api-client";
 *   const data = await api.get<{ status: string }>("/healthz");
 *
 * Usage (authenticated):
 *   import { fetchWithAuth } from "@/lib/api-client";
 *   const data = await fetchWithAuth<User>("/internal/me", {}, idToken);
 */

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000/api";

// ------------------------------------------------------------------ //
// Error type
// ------------------------------------------------------------------ //

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ------------------------------------------------------------------ //
// Core fetch helper (internal)
// ------------------------------------------------------------------ //

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;

  // Only attach JSON Content-Type when we'll actually JSON.stringify a body.
  // Avoids breaking FormData uploads (browser must set multipart boundary).
  const willSendJson = body !== undefined;
  const headers: HeadersInit = {
    ...(willSendJson ? { "Content-Type": "application/json" } : {}),
    ...init?.headers,
  };

  // Spread `init` FIRST so explicit method/headers/body below win (previously
  // init.headers was silently wiping Content-Type → FastAPI returned 422).
  const response = await fetch(url, {
    ...init,
    method,
    headers,
    body: willSendJson ? JSON.stringify(body) : init?.body,
  });

  if (!response.ok) {
    let message = response.statusText;
    try {
      const err = await response.json();
      const raw = err?.detail ?? err?.message ?? message;
      message = typeof raw === "string" ? raw : JSON.stringify(raw);
    } catch {
      // ignore JSON parse failure — keep statusText
    }
    // Session expired / token invalid — sign out and bounce to landing.
    if (response.status === 401 && typeof window !== "undefined") {
      const { signOut } = await import("next-auth/react");
      void signOut({ callbackUrl: "/" });
    }
    throw new ApiError(response.status, message);
  }

  return response.json() as Promise<T>;
}

// ------------------------------------------------------------------ //
// Public API — anonymous / no auth required
// ------------------------------------------------------------------ //

export const api = {
  get<T>(path: string, init?: RequestInit): Promise<T> {
    return request<T>("GET", path, undefined, init);
  },

  post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return request<T>("POST", path, body, init);
  },

  put<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
    return request<T>("PUT", path, body, init);
  },

  delete<T>(path: string, init?: RequestInit): Promise<T> {
    return request<T>("DELETE", path, undefined, init);
  },
} as const;

// ------------------------------------------------------------------ //
// Authenticated API — injects Bearer token for protected routes
// ------------------------------------------------------------------ //

/**
 * Fetch helper for routes that require a valid Entra ID bearer token.
 *
 * @param path    API path relative to NEXT_PUBLIC_API_URL (e.g. "/auth/me")
 * @param init    Optional RequestInit (method, body, extra headers, etc.)
 * @param idToken The id_token from the NextAuth session (session.idToken).
 *                Pass undefined to send without Authorization header —
 *                the backend will return 401.
 */
export async function fetchWithAuth<T>(
  path: string,
  init: RequestInit = {},
  idToken: string | undefined,
): Promise<T> {
  const authHeaders: HeadersInit = idToken
    ? { Authorization: `Bearer ${idToken}` }
    : {};

  return request<T>(
    init.method ?? "GET",
    path,
    undefined, // body passed via init.body for non-GET; use fetchWithAuthBody below
    {
      ...init,
      headers: {
        ...authHeaders,
        ...init.headers,
      },
    },
  );
}

/**
 * Variant of fetchWithAuth that also serialises a JSON body.
 * Use for POST/PUT/PATCH to protected endpoints.
 */
export async function fetchWithAuthBody<T>(
  path: string,
  body: unknown,
  init: RequestInit = {},
  idToken: string | undefined,
): Promise<T> {
  const authHeaders: HeadersInit = idToken
    ? { Authorization: `Bearer ${idToken}` }
    : {};

  return request<T>(init.method ?? "POST", path, body, {
    ...init,
    headers: {
      ...authHeaders,
      ...init.headers,
    },
  });
}

/**
 * Returns a raw fetch Response for SSE streaming endpoints.
 * The caller is responsible for reading response.body as a ReadableStream.
 *
 * Use this (via parseSseStream) for /api/internal/chat and /api/external/chat.
 * Does NOT call response.json() — returns the raw Response so the caller
 * can pipe it through parseSseStream.
 *
 * @param endpoint  API path (e.g. "/internal/chat")
 * @param body      JSON-serialisable request body
 * @param idToken   Optional Bearer token — only attach for internal mode
 * @param mode      "internal" | "external" — controls credentials and auth header
 */
export async function streamChat(
  endpoint: string,
  body: Record<string, unknown>,
  idToken?: string | null,
  mode: "internal" | "external" = "external",
): Promise<Response> {
  const url = `${BASE_URL}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (mode === "internal" && idToken) {
    headers["Authorization"] = `Bearer ${idToken}`;
  }

  return fetch(url, {
    method: "POST",
    headers,
    credentials: mode === "external" ? "include" : "same-origin",
    body: JSON.stringify(body),
  });
}
