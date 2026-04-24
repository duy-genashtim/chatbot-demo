"use client";

/**
 * Admin Documents page — upload form + document list with delete.
 * Polls list after upload to show status transitions.
 */

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import { adminApi, AdminDocument } from "@/lib/admin-api";
import { DocumentUploadForm } from "@/components/admin/document-upload-form";
import { DocumentListTable } from "@/components/admin/document-list-table";
import type { EntraSession } from "@/lib/auth-config";

export default function DocumentsPage() {
  const { data: session } = useSession();
  const idToken = (session as EntraSession | null)?.idToken;

  const [documents, setDocuments] = useState<AdminDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const docs = await adminApi.listDocuments(idToken);
      setDocuments(docs);
    } catch {
      setError("Không tải được danh sách tài liệu.");
    } finally {
      setLoading(false);
    }
  }, [idToken]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll every 5s while any doc is in processing state
  useEffect(() => {
    const hasProcessing = documents.some((d) => d.status === "processing");
    if (!hasProcessing) return;
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [documents, refresh]);

  return (
    <div className="space-y-8 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Tài liệu</h1>
        <p className="text-sm text-gray-500 mt-1">
          Tải lên file PDF để nạp vào pipeline RAG. Quá trình xử lý chạy nền.
        </p>
      </div>

      <DocumentUploadForm idToken={idToken} onUploaded={refresh} />

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-700">Tài liệu đã nạp</h2>
          <button
            onClick={refresh}
            className="text-sm text-brand hover:underline"
          >
            Làm mới
          </button>
        </div>

        {loading && <p className="text-sm text-gray-400">Đang tải…</p>}
        {error && <p className="text-red-600 text-sm">{error}</p>}
        {!loading && (
          <DocumentListTable
            documents={documents}
            idToken={idToken}
            onDeleted={refresh}
          />
        )}
      </div>
    </div>
  );
}
