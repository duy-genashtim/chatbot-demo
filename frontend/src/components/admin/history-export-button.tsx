"use client";

/**
 * Export CSV button — builds the CSV download URL from current filters
 * and triggers a browser download by navigating to it with the Bearer token
 * injected via a signed short-lived URL approach is not feasible here;
 * instead we use fetch + blob + createObjectURL so the auth header is sent.
 */

import { useState } from "react";
import { adminApi, HistoryFilters } from "@/lib/admin-api";

interface Props {
  filters: HistoryFilters;
  idToken: string | undefined;
}

export function HistoryExportButton({ filters, idToken }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setError(null);
    setLoading(true);
    try {
      const url = adminApi.exportCsvUrl(filters);
      const resp = await fetch(url, {
        headers: idToken ? { Authorization: `Bearer ${idToken}` } : {},
      });
      if (!resp.ok) {
        setError(`Xuất thất bại: ${resp.statusText}`);
        return;
      }
      const blob = await resp.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = "chat_history.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      setError("Xuất thất bại. Kiểm tra lại kết nối.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="inline-flex flex-col gap-1">
      <button
        onClick={handleExport}
        disabled={loading}
        className="px-4 py-1.5 rounded text-sm font-medium border border-gray-300 bg-white hover:bg-gray-50 disabled:opacity-50"
      >
        {loading ? "Đang xuất…" : "Xuất CSV"}
      </button>
      {error && <span className="text-red-600 text-xs">{error}</span>}
    </div>
  );
}
