"use client";

/**
 * Modal showing full conversation for a single session_id.
 * Fetches turns on open; renders role-aligned chat bubbles + meta footer.
 */

import { useEffect, useState } from "react";
import { adminApi, ChatTurnRow } from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";

interface Props {
  sessionId: string | null;
  idToken: string | undefined;
  onClose: () => void;
  onDeleted?: (sessionId: string) => void;
}

export function SessionDetailModal({
  sessionId,
  idToken,
  onClose,
  onDeleted,
}: Props) {
  const [turns, setTurns] = useState<ChatTurnRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    setTurns([]);
    adminApi
      .getSessionDetail(sessionId, idToken)
      .then((d) => setTurns(d.turns))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Tải dữ liệu thất bại."),
      )
      .finally(() => setLoading(false));
  }, [sessionId, idToken]);

  if (!sessionId) return null;

  async function handleDelete() {
    if (!sessionId) return;
    if (!confirm("Xóa toàn bộ cuộc trò chuyện này? Hành động không thể hoàn tác.")) return;
    setDeleting(true);
    try {
      await adminApi.deleteSession(sessionId, idToken);
      onDeleted?.(sessionId);
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xóa thất bại.");
    } finally {
      setDeleting(false);
    }
  }

  function copySessionId() {
    if (sessionId) void navigator.clipboard.writeText(sessionId);
  }

  const downloadUrl =
    (process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
      "http://localhost:8000/api") +
    `/admin/history/export.csv?session_id=${encodeURIComponent(sessionId)}`;

  const first = turns[0];
  const last = turns[turns.length - 1];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-3xl max-h-[90vh] rounded-lg shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-3 border-b">
          <div className="min-w-0">
            <h2 className="font-semibold text-gray-800">Cuộc trò chuyện</h2>
            <button
              onClick={copySessionId}
              className="text-xs text-gray-500 font-mono truncate hover:text-gray-800"
              title="Sao chép ID phiên"
            >
              {sessionId}
            </button>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <a
              href={downloadUrl}
              className="px-3 py-1 text-sm border rounded hover:bg-gray-50"
              title="Xuất cuộc trò chuyện này ra CSV"
            >
              Xuất CSV
            </a>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="px-3 py-1 text-sm text-white bg-red-600 hover:bg-red-700 rounded disabled:opacity-50"
            >
              {deleting ? "Đang xóa…" : "Xóa"}
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1 text-sm border rounded hover:bg-gray-50"
            >
              Đóng
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-5 py-4 bg-gray-50">
          {loading && <p className="text-sm text-gray-500">Đang tải…</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {!loading && !error && turns.length === 0 && (
            <p className="text-sm text-gray-500">Không có lượt nào.</p>
          )}
          <div className="space-y-3">
            {turns.map((t) => {
              const isUser = t.role === "user";
              return (
                <div
                  key={t.id}
                  className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
                      isUser
                        ? "bg-blue-600 text-white"
                        : "bg-white text-gray-800 border"
                    }`}
                  >
                    <div className="text-xs opacity-70 mb-1">
                      {t.role}
                      {t.created_at &&
                        ` • ${new Date(t.created_at).toLocaleString()}`}
                      {t.latency_ms != null && ` • ${t.latency_ms}ms`}
                      {t.tokens_out != null && ` • out:${t.tokens_out}`}
                      {t.tokens_in != null && ` • in:${t.tokens_in}`}
                    </div>
                    <div>{t.content}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer meta */}
        {turns.length > 0 && (
          <div className="px-5 py-2 border-t text-xs text-gray-500 flex flex-wrap gap-x-4 gap-y-1">
            <span>Lượt: {turns.length}</span>
            <span>Người dùng: {first?.user_key ?? "—"}</span>
            <span>Chế độ: {first?.mode ?? "—"}</span>
            <span>
              Khoảng:{" "}
              {first?.created_at
                ? new Date(first.created_at).toLocaleString()
                : "—"}{" "}
              →{" "}
              {last?.created_at
                ? new Date(last.created_at).toLocaleString()
                : "—"}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
