"use client";

/**
 * Document upload form — file picker + domain selector + invalidate-cache checkbox.
 * Posts to POST /api/admin/documents/upload via adminApi.
 */

import { useState, useRef } from "react";
import { adminApi, Domain } from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";

// Backend domain enum is still internal_hr / external_policy so we keep the
// values; only the user-facing labels are simplified to Internal / External.
const DOMAINS: { value: Domain; label: string }[] = [
  { value: "internal_hr", label: "Nội bộ" },
  { value: "external_policy", label: "Bên ngoài" },
];

interface Props {
  idToken: string | undefined;
  onUploaded: () => void;
}

export function DocumentUploadForm({ idToken, onUploaded }: Props) {
  const [domain, setDomain] = useState<Domain>("internal_hr");
  const [invalidateCache, setInvalidateCache] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError("Vui lòng chọn file PDF.");
      return;
    }
    setLoading(true);
    try {
      const res = await adminApi.uploadDocument(file, domain, invalidateCache, idToken);
      setSuccess(`Đã tiếp nhận: ${res.filename} — ${res.message}`);
      if (fileRef.current) fileRef.current.value = "";
      onUploaded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Tải lên thất bại.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 border rounded-lg bg-gray-50">
      <h3 className="font-semibold text-gray-700">Tải lên PDF</h3>

      <div className="flex flex-col gap-1">
        <label className="text-sm text-gray-600">File (chỉ PDF)</label>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,application/pdf"
          className="text-sm"
          disabled={loading}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-sm text-gray-600">Miền</label>
        <select
          value={domain}
          onChange={(e) => setDomain(e.target.value as Domain)}
          className="border rounded px-2 py-1 text-sm"
          disabled={loading}
        >
          {DOMAINS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>
      </div>

      <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
        <input
          type="checkbox"
          checked={invalidateCache}
          onChange={(e) => setInvalidateCache(e.target.checked)}
          disabled={loading}
        />
        Vô hiệu hóa cache Gemini ngay
      </label>

      {error && <p className="text-red-600 text-sm">{error}</p>}
      {success && <p className="text-green-600 text-sm">{success}</p>}

      <button
        type="submit"
        disabled={loading}
        className="px-4 py-2 rounded text-sm font-medium text-white disabled:opacity-50"
        style={{ backgroundColor: "var(--brand-primary, #253956)" }}
      >
        {loading ? "Đang tải lên…" : "Tải lên"}
      </button>
    </form>
  );
}
