"use client";

/**
 * Admin History page — two tabs:
 *   - Sessions (default): grouped per session_id with drill-down modal
 *   - Turns (raw): flat per-turn browser (legacy)
 * Shared filters drive CSV export + Purge.
 */

import { useState } from "react";
import { useSession } from "next-auth/react";
import { adminApi, HistoryFilters } from "@/lib/admin-api";
import { SessionsBrowser } from "@/components/admin/sessions-browser";
import { HistoryBrowser } from "@/components/admin/history-browser";
import { HistoryExportButton } from "@/components/admin/history-export-button";
import { ApiError } from "@/lib/api-client";
import type { EntraSession } from "@/lib/auth-config";

type Tab = "sessions" | "turns";

export default function HistoryPage() {
  const { data: session } = useSession();
  const idToken = (session as EntraSession | null)?.idToken;

  const [tab, setTab] = useState<Tab>("sessions");
  const [filters, setFilters] = useState<HistoryFilters>({});
  const [purging, setPurging] = useState(false);
  const [purgeResult, setPurgeResult] = useState<string | null>(null);
  const [purgeError, setPurgeError] = useState<string | null>(null);

  async function handlePurge() {
    if (
      !confirm(
        "Hành động này sẽ xóa vĩnh viễn các bản ghi lịch sử trò chuyện khớp bộ lọc. Tiếp tục?",
      )
    )
      return;
    if (
      !confirm(
        "Xác nhận lần hai: hành động này KHÔNG THỂ hoàn tác. Tiếp tục xóa?",
      )
    )
      return;

    setPurging(true);
    setPurgeResult(null);
    setPurgeError(null);
    try {
      const result = await adminApi.purgeHistory(filters, idToken);
      setPurgeResult(`Đã xóa ${result.deleted} lượt.`);
    } catch (err) {
      setPurgeError(err instanceof ApiError ? err.message : "Xóa thất bại.");
    } finally {
      setPurging(false);
    }
  }

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Lịch sử trò chuyện</h1>
          <p className="text-sm text-gray-500 mt-1">
            Duyệt, xuất hoặc xóa các lượt trò chuyện. Dùng bộ lọc ở tab Phiên
            để giới hạn phạm vi xuất / xóa.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <HistoryExportButton filters={filters} idToken={idToken} />
          <button
            onClick={handlePurge}
            disabled={purging}
            className="px-4 py-1.5 rounded text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50"
          >
            {purging ? "Đang xóa…" : "Xóa kết quả lọc"}
          </button>
        </div>
      </div>

      {purgeResult && <p className="text-green-600 text-sm">{purgeResult}</p>}
      {purgeError && <p className="text-red-600 text-sm">{purgeError}</p>}

      {/* Tabs */}
      <div className="border-b flex gap-1">
        <TabButton active={tab === "sessions"} onClick={() => setTab("sessions")}>
          Phiên
        </TabButton>
        <TabButton active={tab === "turns"} onClick={() => setTab("turns")}>
          Lượt (thô)
        </TabButton>
      </div>

      {tab === "sessions" ? (
        <SessionsBrowser
          idToken={idToken}
          filters={filters}
          onFiltersChange={setFilters}
        />
      ) : (
        <>
          <p className="text-xs text-gray-500">
            Chế độ xem thô theo từng lượt. Bộ lọc ở đây độc lập; dùng bộ lọc tab
            Phiên cho phạm vi xuất/xóa.
          </p>
          <HistoryBrowser idToken={idToken} />
        </>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
        active
          ? "border-[var(--brand-primary,#253956)] text-gray-900"
          : "border-transparent text-gray-500 hover:text-gray-800"
      }`}
    >
      {children}
    </button>
  );
}
