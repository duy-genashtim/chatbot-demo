"use client";

/**
 * Modal showing on-demand chunk-level details for a document.
 * Fetches /admin/documents/{doc_id}/details when opened.
 */

import { useEffect, useState } from "react";
import { adminApi, DocumentDetails } from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";

interface Props {
  docId: string | null;
  idToken: string | undefined;
  onClose: () => void;
}

export function DocumentDetailModal({ docId, idToken, onClose }: Props) {
  const [data, setData] = useState<DocumentDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!docId) return;
    setLoading(true);
    setError(null);
    setData(null);
    adminApi
      .getDocumentDetails(docId, idToken, { previewLimit: 10, previewChars: 600 })
      .then(setData)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Tải dữ liệu thất bại."),
      )
      .finally(() => setLoading(false));
  }, [docId, idToken]);

  if (!docId) return null;

  const d = data?.document;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white w-full max-w-4xl max-h-[90vh] rounded-lg shadow-xl flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-3 border-b">
          <div className="min-w-0">
            <h2 className="font-semibold text-gray-800 truncate">
              {d?.filename ?? "Chi tiết tài liệu"}
            </h2>
            <div className="text-xs text-gray-500 font-mono truncate">
              {docId}
            </div>
          </div>
          <button
            onClick={onClose}
            className="px-3 py-1 text-sm border rounded hover:bg-gray-50"
          >
            Đóng
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto px-5 py-4 space-y-4">
          {loading && <p className="text-sm text-gray-500">Đang tải…</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}

          {data && (
            <>
              {/* Document metadata */}
              <section className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <Stat label="Miền" value={d?.domain ?? "—"} />
                <Stat label="Trạng thái" value={d?.status ?? "—"} />
                <Stat
                  label="Kích thước"
                  value={d ? formatBytes(d.size_bytes) : "—"}
                />
                <Stat
                  label="Đã tải lên"
                  value={
                    d?.uploaded_at
                      ? new Date(d.uploaded_at).toLocaleString()
                      : "—"
                  }
                />
                <Stat label="Người tải lên" value={d?.uploaded_by || "—"} />
              </section>

              {d?.error_msg && (
                <section>
                  <div className="text-xs text-gray-500 mb-1">Lỗi</div>
                  <pre className="text-xs bg-red-50 border border-red-200 text-red-800 p-2 rounded whitespace-pre-wrap">
                    {d.error_msg}
                  </pre>
                </section>
              )}

              {/* Chunk aggregates */}
              <section className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm bg-gray-50 border rounded p-3">
                <Stat
                  label="Số chunk"
                  value={data.chunk_count.toLocaleString()}
                />
                <Stat
                  label="Tổng ký tự"
                  value={data.total_chars.toLocaleString()}
                />
                <Stat
                  label="Trung bình ký tự / chunk"
                  value={data.avg_chunk_chars.toLocaleString()}
                />
                <Stat
                  label="Khoảng trang"
                  value={
                    data.page_start_min != null && data.page_start_max != null
                      ? `${data.page_start_min} – ${data.page_start_max}`
                      : "—"
                  }
                />
                <Stat
                  label="Số mục"
                  value={String(data.unique_sections.length)}
                />
              </section>

              {/* Section list */}
              {data.unique_sections.length > 0 && (
                <section>
                  <div className="text-xs text-gray-500 mb-1">
                    Mục ({data.unique_sections.length})
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {data.unique_sections.map((s) => (
                      <span
                        key={s}
                        className="text-xs px-2 py-0.5 bg-gray-100 border rounded"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {/* Chunk preview */}
              <section>
                <div className="text-xs text-gray-500 mb-2">
                  Xem trước chunk ({data.preview.length} đầu tiên trong tổng {data.chunk_count})
                </div>
                <div className="space-y-3">
                  {data.preview.map((p) => (
                    <div
                      key={p.chunk_index}
                      className="border rounded p-3 bg-white"
                    >
                      <div className="text-xs text-gray-500 mb-1 flex flex-wrap gap-x-3">
                        <span>#{p.chunk_index}</span>
                        {p.page_start != null && <span>trang {p.page_start}</span>}
                        {p.section && <span>{p.section}</span>}
                        <span>{p.chars.toLocaleString()} ký tự</span>
                      </div>
                      <pre className="text-xs text-gray-800 whitespace-pre-wrap font-sans">
                        {p.text}
                      </pre>
                    </div>
                  ))}
                  {data.preview.length === 0 && (
                    <p className="text-sm text-gray-400">Không tìm thấy chunk nào.</p>
                  )}
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-gray-500">{label}</div>
      <div className="font-medium text-gray-800 break-words">{value}</div>
    </div>
  );
}

function formatBytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
}
