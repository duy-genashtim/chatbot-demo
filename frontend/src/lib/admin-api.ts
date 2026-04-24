/**
 * Typed admin API client.
 *
 * All calls hit /api/admin/* and require a valid Entra ID bearer token.
 * Pass session.idToken from useSession() or auth().
 *
 * Usage:
 *   import { adminApi } from "@/lib/admin-api";
 *   const docs = await adminApi.listDocuments(idToken);
 */

import { fetchWithAuth, fetchWithAuthBody, ApiError } from "@/lib/api-client";

// ------------------------------------------------------------------ //
// Domain types
// ------------------------------------------------------------------ //

export type DocStatus = "processing" | "ready" | "failed";
export type Domain = "internal_hr" | "external_policy";

export interface AdminDocument {
  id: number;
  doc_id: string;
  filename: string;
  domain: Domain;
  size_bytes: number;
  uploaded_by: string;
  uploaded_at: string;
  status: DocStatus;
  error_msg: string | null;
}

export interface UploadResponse {
  status: string;
  filename: string;
  domain: string;
  message: string;
}

export interface DocumentChunkPreview {
  chunk_index: number;
  section: string;
  page_start: number | null;
  chars: number;
  text: string;
}

export interface DocumentDetails {
  document: AdminDocument;
  chunk_count: number;
  total_chars: number;
  avg_chunk_chars: number;
  page_start_min: number | null;
  page_start_max: number | null;
  unique_sections: string[];
  preview: DocumentChunkPreview[];
}

export type SettingType = "string" | "number" | "integer" | "boolean" | "text";

export interface SettingSchema {
  type: SettingType;
  default: unknown;
  label: string;
  min?: number;
  max?: number;
}

export type SettingsSchemaMap = Record<string, SettingSchema>;
export type SettingsValuesMap = Record<string, unknown>;

/**
 * Response shape from PUT /admin/settings.
 *
 * `cache_rebuild_pending` + `note` are present only when a setting that
 * affects a Gemini context cache changed (e.g. INTERNAL/EXTERNAL_REQUIRE_CITATIONS).
 */
export interface UpdateSettingsResponse {
  updated: string[];
  cache_rebuild_pending?: string[];
  note?: string;
}

export interface AdminEntry {
  email: string;
  created_at: string | null;
}

export interface ChatTurnRow {
  id: number;
  session_id: string;
  user_key: string;
  mode: string;
  role: string;
  content: string;
  tokens_in: number | null;
  tokens_cached: number | null;
  tokens_out: number | null;
  latency_ms: number | null;
  created_at: string | null;
}

export interface SessionSummary {
  session_id: string;
  user_key: string;
  mode: string;
  turn_count: number;
  first_at: string | null;
  last_at: string | null;
  tokens_in_sum: number;
  tokens_out_sum: number;
  tokens_cached_sum: number;
  avg_latency_ms: number | null;
}

export interface SessionListResponse {
  total: number;
  items: SessionSummary[];
}

export interface SessionDetail {
  session_id: string;
  turns: ChatTurnRow[];
}

export interface HistoryStats {
  sessions: number;
  turns: number;
  tokens_in: number;
  tokens_out: number;
  tokens_cached: number;
  avg_latency_ms: number | null;
}

export interface HistoryFilters {
  mode?: string;
  user_key?: string;
  since?: string;
  until?: string;
  session_id?: string;
}

// ------------------------------------------------------------------ //
// Helper to build query string
// ------------------------------------------------------------------ //

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (!entries.length) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

// ------------------------------------------------------------------ //
// Admin API object
// ------------------------------------------------------------------ //

export const adminApi = {
  // ---- Documents -------------------------------------------------- //

  async uploadDocument(
    file: File,
    domain: Domain,
    invalidateCache: boolean,
    idToken: string | undefined,
  ): Promise<UploadResponse> {
    const form = new FormData();
    form.append("file", file);
    return fetchWithAuth<UploadResponse>(
      `/admin/documents/upload?domain=${domain}&invalidate_cache=${invalidateCache}`,
      { method: "POST", body: form },
      idToken,
    );
  },

  async listDocuments(
    idToken: string | undefined,
    domain?: Domain,
  ): Promise<AdminDocument[]> {
    const qs = domain ? `?domain=${domain}` : "";
    return fetchWithAuth<AdminDocument[]>(`/admin/documents${qs}`, {}, idToken);
  },

  async deleteDocument(
    docId: string,
    invalidateCache: boolean,
    idToken: string | undefined,
  ): Promise<{ deleted: string }> {
    return fetchWithAuth<{ deleted: string }>(
      `/admin/documents/${docId}?invalidate_cache=${invalidateCache}`,
      { method: "DELETE" },
      idToken,
    );
  },

  async getDocumentDetails(
    docId: string,
    idToken: string | undefined,
    opts: { previewLimit?: number; previewChars?: number } = {},
  ): Promise<DocumentDetails> {
    const qs = buildQuery({
      preview_limit: opts.previewLimit,
      preview_chars: opts.previewChars,
    });
    return fetchWithAuth<DocumentDetails>(
      `/admin/documents/${encodeURIComponent(docId)}/details${qs}`,
      {},
      idToken,
    );
  },

  // ---- Settings --------------------------------------------------- //

  async getSettingsSchema(idToken: string | undefined): Promise<SettingsSchemaMap> {
    return fetchWithAuth<SettingsSchemaMap>("/admin/settings/schema", {}, idToken);
  },

  async getSettings(idToken: string | undefined): Promise<SettingsValuesMap> {
    return fetchWithAuth<SettingsValuesMap>("/admin/settings", {}, idToken);
  },

  async updateSettings(
    values: SettingsValuesMap,
    idToken: string | undefined,
  ): Promise<UpdateSettingsResponse> {
    return fetchWithAuthBody<UpdateSettingsResponse>(
      "/admin/settings",
      values,
      { method: "PUT" },
      idToken,
    );
  },

  // ---- Admins ----------------------------------------------------- //

  async listAdmins(idToken: string | undefined): Promise<AdminEntry[]> {
    return fetchWithAuth<AdminEntry[]>("/admin/admins", {}, idToken);
  },

  async addAdmin(
    email: string,
    idToken: string | undefined,
  ): Promise<AdminEntry> {
    return fetchWithAuthBody<AdminEntry>(
      "/admin/admins",
      { email },
      { method: "POST" },
      idToken,
    );
  },

  async removeAdmin(
    email: string,
    idToken: string | undefined,
  ): Promise<{ removed: string }> {
    return fetchWithAuth<{ removed: string }>(
      `/admin/admins/${encodeURIComponent(email)}`,
      { method: "DELETE" },
      idToken,
    );
  },

  // ---- History ---------------------------------------------------- //

  async listHistory(
    filters: HistoryFilters & { limit?: number; offset?: number },
    idToken: string | undefined,
  ): Promise<ChatTurnRow[]> {
    const qs = buildQuery(filters as Record<string, string | undefined>);
    return fetchWithAuth<ChatTurnRow[]>(`/admin/history${qs}`, {}, idToken);
  },

  exportCsvUrl(filters: HistoryFilters): string {
    const BASE =
      (process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000/api");
    const qs = buildQuery(filters as Record<string, string | undefined>);
    return `${BASE}/admin/history/export.csv${qs}`;
  },

  async purgeHistory(
    filters: HistoryFilters,
    idToken: string | undefined,
  ): Promise<{ deleted: number }> {
    const qs = buildQuery(filters as Record<string, string | undefined>);
    return fetchWithAuth<{ deleted: number }>(
      `/admin/history${qs}`,
      { method: "DELETE", headers: { "X-Confirm-Delete": "yes" } },
      idToken,
    );
  },

  async listSessions(
    filters: HistoryFilters & { limit?: number; offset?: number },
    idToken: string | undefined,
  ): Promise<SessionListResponse> {
    const qs = buildQuery(filters as Record<string, string | undefined>);
    return fetchWithAuth<SessionListResponse>(
      `/admin/history/sessions${qs}`,
      {},
      idToken,
    );
  },

  async getSessionDetail(
    sessionId: string,
    idToken: string | undefined,
  ): Promise<SessionDetail> {
    return fetchWithAuth<SessionDetail>(
      `/admin/history/sessions/${encodeURIComponent(sessionId)}`,
      {},
      idToken,
    );
  },

  async deleteSession(
    sessionId: string,
    idToken: string | undefined,
  ): Promise<{ deleted: number; session_id: string }> {
    return fetchWithAuth<{ deleted: number; session_id: string }>(
      `/admin/history/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE", headers: { "X-Confirm-Delete": "yes" } },
      idToken,
    );
  },

  async getHistoryStats(
    filters: HistoryFilters,
    idToken: string | undefined,
  ): Promise<HistoryStats> {
    const qs = buildQuery(filters as Record<string, string | undefined>);
    return fetchWithAuth<HistoryStats>(
      `/admin/history/stats${qs}`,
      {},
      idToken,
    );
  },
};

export { ApiError };
