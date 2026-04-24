"use client";

/**
 * Admin allowlist editor — shows current admins, add-email input, remove buttons.
 * Wraps GET/POST/DELETE /api/admin/admins via adminApi.
 */

import { useEffect, useState } from "react";
import { adminApi, AdminEntry } from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";

interface Props {
  admins: AdminEntry[];
  currentUserEmail: string;
  idToken: string | undefined;
  onChanged: () => void;
}

export function AdminListEditor({
  admins,
  currentUserEmail,
  idToken,
  onChanged,
}: Props) {
  const [newEmail, setNewEmail] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingEmail, setRemovingEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  // Defer locale-dependent date rendering until after hydration.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const trimmed = newEmail.trim().toLowerCase();
    if (!trimmed) return;
    setAdding(true);
    try {
      await adminApi.addAdmin(trimmed, idToken);
      setNewEmail("");
      setSuccess(`Đã thêm: ${trimmed}`);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Thêm thất bại.");
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(email: string) {
    if (!confirm(`Xóa quản trị viên "${email}"? Họ sẽ mất quyền quản trị ngay lập tức.`)) return;
    setError(null);
    setSuccess(null);
    setRemovingEmail(email);
    try {
      await adminApi.removeAdmin(email, idToken);
      setSuccess(`Đã xóa: ${email}`);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Xóa thất bại.");
    } finally {
      setRemovingEmail(null);
    }
  }

  return (
    <div className="space-y-5">
      {/* Current admins table */}
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-100 text-left text-gray-600">
            <th className="px-3 py-2 border">Email</th>
            <th className="px-3 py-2 border">Ngày thêm</th>
            <th className="px-3 py-2 border">Thao tác</th>
          </tr>
        </thead>
        <tbody>
          {admins.map((a) => (
            <tr key={a.email} className="hover:bg-gray-50">
              <td className="px-3 py-2 border font-mono text-xs">
                {a.email}
                {a.email === currentUserEmail && (
                  <span className="ml-2 text-xs text-brand opacity-60">(bạn)</span>
                )}
              </td>
              <td className="px-3 py-2 border text-xs">
                {mounted && a.created_at
                  ? new Date(a.created_at).toLocaleDateString()
                  : "—"}
              </td>
              <td className="px-3 py-2 border">
                {a.email !== currentUserEmail && (
                  <button
                    onClick={() => handleRemove(a.email)}
                    disabled={removingEmail === a.email}
                    className="text-red-600 hover:underline text-xs disabled:opacity-40"
                  >
                    {removingEmail === a.email ? "Đang xóa…" : "Xóa"}
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Add new admin */}
      <form onSubmit={handleAdd} className="flex items-center gap-3">
        <input
          type="email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          placeholder="quan-tri-vien-moi@example.com"
          className="border rounded px-3 py-1.5 text-sm flex-1 max-w-xs"
          disabled={adding}
        />
        <button
          type="submit"
          disabled={adding || !newEmail.trim()}
          className="px-4 py-1.5 rounded text-sm font-medium text-white disabled:opacity-50"
          style={{ backgroundColor: "var(--brand-primary, #253956)" }}
        >
          {adding ? "Đang thêm…" : "Thêm quản trị viên"}
        </button>
      </form>

      {error && <p className="text-red-600 text-sm">{error}</p>}
      {success && <p className="text-green-600 text-sm">{success}</p>}
    </div>
  );
}
