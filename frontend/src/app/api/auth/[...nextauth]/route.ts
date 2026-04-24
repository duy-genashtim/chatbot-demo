/**
 * NextAuth (Auth.js v5) App Router catch-all route.
 *
 * Delegates all GET and POST requests under /api/auth/* to the
 * configured handlers exported from auth-config.ts.
 * This covers the sign-in, callback, sign-out, and session endpoints.
 */

import { handlers } from "@/lib/auth-config";

export const { GET, POST } = handlers;
