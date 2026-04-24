"use client";

/**
 * History browser — filter bar + paginated turn table.
 * Uses adminApi.listHistory with mode/user_key/since/until/limit/offset.
 */

import { useState, useCallback, useEffect } from "react";
import { adminApi, ChatTurnRow, HistoryFilters } from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";

const PAGE_SIZE = 50;

interface Props {
  idToken: string | undefined;
}

export function HistoryBrowser({ idToken }: Props) {
  const [filters, setFilters] = useState<HistoryFilters>({});
  const [page, setPage] = useState(0);
  const [turns, setTurns] = useState<ChatTurnRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  // Defer locale-dependent date rendering until after hydration.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const fetchTurns = useCallback(
    async (activeFilters: HistoryFilters, pageNum: number) => {
      setLoading(true);
      setError(null);
      try {
        const rows = await adminApi.listHistory(
          { ...activeFilters, limit: PAGE_SIZE, offset: pageNum * PAGE_SIZE },
          idToken,
        );
        setTurns(rows);
        setSearched(true);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Tải dữ liệu thất bại.");
      } finally {
        setLoading(false);
      }
    },
    [idToken],
  );

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(0);
    fetchTurns(filters, 0);
  }

  function handlePageChange(delta: number) {
    const next = page + delta;
    if (next < 0) return;
    setPage(next);
    fetchTurns(filters, next);
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <form onSubmit={handleSearch} className="flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Chế độ</label>
          <select
            value={filters.mode ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, mode: e.target.value || undefined }))
            }
            className="border rounded px-2 py-1 text-sm"
          >
            <option value="">Tất cả</option>
            <option value="internal">Nội bộ</option>
            <option value="external">Bên ngoài</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Khóa người dùng</label>
          <input
            type="text"
            value={filters.user_key ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, user_key: e.target.value || undefined }))
            }
            placeholder="email hoặc id phiên"
            className="border rounded px-2 py-1 text-sm w-48"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Từ</label>
          <input
            type="datetime-local"
            value={filters.since ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, since: e.target.value || undefined }))
            }
            className="border rounded px-2 py-1 text-sm"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Đến</label>
          <input
            type="datetime-local"
            value={filters.until ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, until: e.target.value || undefined }))
            }
            className="border rounded px-2 py-1 text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="px-4 py-1.5 rounded text-sm font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: "var(--brand-primary, #253956)" }}
        >
          {loading ? "Đang tải…" : "Tìm kiếm"}
        </button>
      </form>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {/* Turns table */}
      {searched && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="bg-gray-100 text-left text-gray-600">
                  <th className="px-2 py-1 border">ID</th>
                  <th className="px-2 py-1 border">Phiên</th>
                  <th className="px-2 py-1 border">Khóa người dùng</th>
                  <th className="px-2 py-1 border">Chế độ</th>
                  <th className="px-2 py-1 border">Vai trò</th>
                  <th className="px-2 py-1 border max-w-xs">Nội dung</th>
                  <th className="px-2 py-1 border">Token vào</th>
                  <th className="px-2 py-1 border">Đã cache</th>
                  <th className="px-2 py-1 border">Token ra</th>
                  <th className="px-2 py-1 border">Độ trễ (ms)</th>
                  <th className="px-2 py-1 border">Tạo lúc</th>
                </tr>
              </thead>
              <tbody>
                {turns.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="px-2 py-3 text-center text-gray-400">
                      Không tìm thấy lượt nào.
                    </td>
                  </tr>
                ) : (
                  turns.map((t) => (
                    <tr key={t.id} className="hover:bg-gray-50">
                      <td className="px-2 py-1 border">{t.id}</td>
                      <td className="px-2 py-1 border font-mono truncate max-w-[120px]">
                        {t.session_id}
                      </td>
                      <td className="px-2 py-1 border truncate max-w-[120px]">
                        {t.user_key}
                      </td>
                      <td className="px-2 py-1 border">{t.mode}</td>
                      <td className="px-2 py-1 border">{t.role}</td>
                      <td
                        className="px-2 py-1 border max-w-xs truncate"
                        title={t.content}
                      >
                        {t.content.slice(0, 80)}
                        {t.content.length > 80 ? "…" : ""}
                      </td>
                      <td className="px-2 py-1 border text-right">{t.tokens_in ?? "—"}</td>
                      <td className="px-2 py-1 border text-right">{t.tokens_cached ?? "—"}</td>
                      <td className="px-2 py-1 border text-right">{t.tokens_out ?? "—"}</td>
                      <td className="px-2 py-1 border text-right">{t.latency_ms ?? "—"}</td>
                      <td className="px-2 py-1 border whitespace-nowrap">
                        {mounted && t.created_at
                          ? new Date(t.created_at).toLocaleString()
                          : "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center gap-3 text-sm">
            <button
              onClick={() => handlePageChange(-1)}
              disabled={page === 0 || loading}
              className="px-3 py-1 border rounded disabled:opacity-40"
            >
              Trước
            </button>
            <span className="text-gray-600">Trang {page + 1}</span>
            <button
              onClick={() => handlePageChange(1)}
              disabled={turns.length < PAGE_SIZE || loading}
              className="px-3 py-1 border rounded disabled:opacity-40"
            >
              Sau
            </button>
          </div>
        </>
      )}
    </div>
  );
}
