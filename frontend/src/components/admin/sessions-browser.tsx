"use client";

/**
 * Sessions browser — groups turns by session_id, shows aggregates per session.
 * Click a row to open SessionDetailModal with full conversation.
 */

import { useState, useCallback, useEffect } from "react";
import {
  adminApi,
  HistoryFilters,
  SessionSummary,
  HistoryStats,
} from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";
import { SessionDetailModal } from "./session-detail-modal";

const PAGE_SIZE = 50;

interface Props {
  idToken: string | undefined;
  filters: HistoryFilters;
  onFiltersChange: (f: HistoryFilters) => void;
}

export function SessionsBrowser({ idToken, filters, onFiltersChange }: Props) {
  const [page, setPage] = useState(0);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const fetchData = useCallback(
    async (activeFilters: HistoryFilters, pageNum: number) => {
      setLoading(true);
      setError(null);
      try {
        const [resp, s] = await Promise.all([
          adminApi.listSessions(
            { ...activeFilters, limit: PAGE_SIZE, offset: pageNum * PAGE_SIZE },
            idToken,
          ),
          adminApi.getHistoryStats(activeFilters, idToken),
        ]);
        setSessions(resp.items);
        setTotal(resp.total);
        setStats(s);
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
    fetchData(filters, 0);
  }

  function handlePageChange(delta: number) {
    const next = page + delta;
    if (next < 0) return;
    setPage(next);
    fetchData(filters, next);
  }

  function handleSessionDeleted(deletedId: string) {
    setSessions((prev) => prev.filter((s) => s.session_id !== deletedId));
    setTotal((t) => Math.max(0, t - 1));
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <form onSubmit={handleSearch} className="flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Chế độ</label>
          <select
            value={filters.mode ?? ""}
            onChange={(e) =>
              onFiltersChange({ ...filters, mode: e.target.value || undefined })
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
              onFiltersChange({
                ...filters,
                user_key: e.target.value || undefined,
              })
            }
            placeholder="email hoặc id phiên"
            className="border rounded px-2 py-1 text-sm w-48"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">ID Phiên</label>
          <input
            type="text"
            value={filters.session_id ?? ""}
            onChange={(e) =>
              onFiltersChange({
                ...filters,
                session_id: e.target.value || undefined,
              })
            }
            placeholder="khớp chính xác"
            className="border rounded px-2 py-1 text-sm w-48 font-mono"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Từ</label>
          <input
            type="datetime-local"
            value={filters.since ?? ""}
            onChange={(e) =>
              onFiltersChange({ ...filters, since: e.target.value || undefined })
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
              onFiltersChange({ ...filters, until: e.target.value || undefined })
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

      {/* Stats banner */}
      {searched && stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-sm bg-gray-50 border rounded p-3">
          <Stat label="Phiên" value={stats.sessions.toLocaleString()} />
          <Stat label="Lượt" value={stats.turns.toLocaleString()} />
          <Stat label="Token vào" value={stats.tokens_in.toLocaleString()} />
          <Stat label="Token ra" value={stats.tokens_out.toLocaleString()} />
          <Stat
            label="Độ trễ TB"
            value={
              stats.avg_latency_ms != null
                ? `${Math.round(stats.avg_latency_ms)} ms`
                : "—"
            }
          />
        </div>
      )}

      {/* Sessions table */}
      {searched && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-gray-100 text-left text-gray-600">
                  <th className="px-2 py-1 border">Phiên</th>
                  <th className="px-2 py-1 border">Người dùng</th>
                  <th className="px-2 py-1 border">Chế độ</th>
                  <th className="px-2 py-1 border text-right">Lượt</th>
                  <th className="px-2 py-1 border text-right">Token vào</th>
                  <th className="px-2 py-1 border text-right">Token ra</th>
                  <th className="px-2 py-1 border text-right">Độ trễ TB</th>
                  <th className="px-2 py-1 border">Đầu tiên</th>
                  <th className="px-2 py-1 border">Cuối cùng</th>
                </tr>
              </thead>
              <tbody>
                {sessions.length === 0 ? (
                  <tr>
                    <td
                      colSpan={9}
                      className="px-2 py-3 text-center text-gray-400"
                    >
                      Không tìm thấy phiên nào.
                    </td>
                  </tr>
                ) : (
                  sessions.map((s) => (
                    <tr
                      key={s.session_id}
                      className="hover:bg-blue-50 cursor-pointer"
                      onClick={() => setActiveSession(s.session_id)}
                    >
                      <td className="px-2 py-1 border font-mono text-xs truncate max-w-[160px]">
                        {s.session_id}
                      </td>
                      <td className="px-2 py-1 border truncate max-w-[140px]">
                        {s.user_key}
                      </td>
                      <td className="px-2 py-1 border">{s.mode}</td>
                      <td className="px-2 py-1 border text-right">
                        {s.turn_count}
                      </td>
                      <td className="px-2 py-1 border text-right">
                        {s.tokens_in_sum}
                      </td>
                      <td className="px-2 py-1 border text-right">
                        {s.tokens_out_sum}
                      </td>
                      <td className="px-2 py-1 border text-right">
                        {s.avg_latency_ms != null
                          ? `${Math.round(s.avg_latency_ms)}ms`
                          : "—"}
                      </td>
                      <td className="px-2 py-1 border whitespace-nowrap text-xs">
                        {mounted && s.first_at
                          ? new Date(s.first_at).toLocaleString()
                          : "—"}
                      </td>
                      <td className="px-2 py-1 border whitespace-nowrap text-xs">
                        {mounted && s.last_at
                          ? new Date(s.last_at).toLocaleString()
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
            <span className="text-gray-600">
              Trang {page + 1} / {totalPages} · {total.toLocaleString()} phiên
            </span>
            <button
              onClick={() => handlePageChange(1)}
              disabled={page + 1 >= totalPages || loading}
              className="px-3 py-1 border rounded disabled:opacity-40"
            >
              Sau
            </button>
          </div>
        </>
      )}

      <SessionDetailModal
        sessionId={activeSession}
        idToken={idToken}
        onClose={() => setActiveSession(null)}
        onDeleted={handleSessionDeleted}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="font-semibold text-gray-800">{value}</div>
    </div>
  );
}
