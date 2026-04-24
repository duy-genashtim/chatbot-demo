"use client";

/**
 * Document list table — renders AdminDocument rows with delete button per row.
 */

import { useEffect, useState } from "react";
import { adminApi, AdminDocument, Domain } from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";
import { DocumentDetailModal } from "./document-detail-modal";

// Friendly label for each backend domain value.
const DOMAIN_LABEL: Record<Domain, string> = {
  internal_hr: "Nội bộ",
  external_policy: "Bên ngoài",
};

interface Props {
  documents: AdminDocument[];
  idToken: string | undefined;
  onDeleted: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  ready: "text-green-600",
  processing: "text-yellow-600",
  failed: "text-red-600",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentListTable({ documents, idToken, onDeleted }: Props) {
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [viewingId, setViewingId] = useState<string | null>(null);
  // Date formatting uses the browser locale/timezone which differs from the
  // SSR pass. Gate it behind a mount flag so the initial render matches the
  // server HTML and the formatted string only appears post-hydration.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  async function handleDelete(docId: string, filename: string) {
    if (!confirm(`Xóa "${filename}"? Hành động này không thể hoàn tác.`)) return;
    setError(null);
    setDeletingId(docId);
    try {
      await adminApi.deleteDocument(docId, true, idToken);
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xóa thất bại.");
    } finally {
      setDeletingId(null);
    }
  }

  if (documents.length === 0) {
    return <p className="text-gray-500 text-sm">Chưa có tài liệu nào được nạp.</p>;
  }

  return (
    <div className="overflow-x-auto">
      {error && <p className="text-red-600 text-sm mb-2">{error}</p>}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-100 text-left text-gray-600">
            <th className="px-3 py-2 border">Tên file</th>
            <th className="px-3 py-2 border">Miền</th>
            <th className="px-3 py-2 border">Kích thước</th>
            <th className="px-3 py-2 border">Người tải lên</th>
            <th className="px-3 py-2 border">Thời gian tải lên</th>
            <th className="px-3 py-2 border">Trạng thái</th>
            <th className="px-3 py-2 border">Thao tác</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.doc_id} className="hover:bg-gray-50">
              <td className="px-3 py-2 border font-mono text-xs">{doc.filename}</td>
              <td className="px-3 py-2 border">{DOMAIN_LABEL[doc.domain] ?? doc.domain}</td>
              <td className="px-3 py-2 border">{formatBytes(doc.size_bytes)}</td>
              <td className="px-3 py-2 border">{doc.uploaded_by}</td>
              <td className="px-3 py-2 border text-xs">
                {mounted && doc.uploaded_at
                  ? new Date(doc.uploaded_at).toLocaleString()
                  : "—"}
              </td>
              <td
                className={`px-3 py-2 border font-medium ${STATUS_COLORS[doc.status] ?? ""}`}
              >
                {doc.status}
                {doc.error_msg && (
                  <span className="ml-1 text-xs text-red-400" title={doc.error_msg}>
                    (!)
                  </span>
                )}
              </td>
              <td className="px-3 py-2 border">
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setViewingId(doc.doc_id)}
                    className="text-brand hover:underline text-xs"
                  >
                    Xem
                  </button>
                  <button
                    onClick={() => handleDelete(doc.doc_id, doc.filename)}
                    disabled={deletingId === doc.doc_id}
                    className="text-red-600 hover:underline text-xs disabled:opacity-40"
                  >
                    {deletingId === doc.doc_id ? "Đang xóa…" : "Xóa"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <DocumentDetailModal
        docId={viewingId}
        idToken={idToken}
        onClose={() => setViewingId(null)}
      />
    </div>
  );
}
