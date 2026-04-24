"use client";

/**
 * Admin Admins page — list current admins + add/remove via AdminListEditor.
 */

import { useState, useEffect, useCallback } from "react";
import { useSession } from "next-auth/react";
import { adminApi, AdminEntry } from "@/lib/admin-api";
import { AdminListEditor } from "@/components/admin/admin-list-editor";
import type { EntraSession } from "@/lib/auth-config";

export default function AdminsPage() {
  const { data: session } = useSession();
  const idToken = (session as EntraSession | null)?.idToken;
  const currentEmail = session?.user?.email ?? "";

  const [admins, setAdmins] = useState<AdminEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const rows = await adminApi.listAdmins(idToken);
      setAdmins(rows);
    } catch {
      setError("Không tải được danh sách quản trị viên.");
    } finally {
      setLoading(false);
    }
  }, [idToken]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Quản trị viên</h1>
        <p className="text-sm text-gray-500 mt-1">
          Quản lý danh sách quản trị viên. Bạn không thể xóa chính mình hoặc quản trị viên cuối cùng.
        </p>
      </div>

      {loading && <p className="text-sm text-gray-400">Đang tải…</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {!loading && (
        <AdminListEditor
          admins={admins}
          currentUserEmail={currentEmail}
          idToken={idToken}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
