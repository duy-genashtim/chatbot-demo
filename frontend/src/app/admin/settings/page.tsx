"use client";

/**
 * Admin Settings page — schema-driven form loaded from backend.
 * Fetches /admin/settings/schema and /admin/settings on mount,
 * delegates rendering to SettingsForm component.
 */

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { adminApi, SettingsSchemaMap, SettingsValuesMap } from "@/lib/admin-api";
import { SettingsForm } from "@/components/admin/settings-form";
import type { EntraSession } from "@/lib/auth-config";

export default function SettingsPage() {
  const { data: session } = useSession();
  const idToken = (session as EntraSession | null)?.idToken;

  const [schema, setSchema] = useState<SettingsSchemaMap | null>(null);
  const [values, setValues] = useState<SettingsValuesMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setError(null);
      try {
        const [s, v] = await Promise.all([
          adminApi.getSettingsSchema(idToken),
          adminApi.getSettings(idToken),
        ]);
        setSchema(s);
        setValues(v);
      } catch {
        setError("Không tải được cài đặt.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [idToken]);

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Cài đặt</h1>
        <p className="text-sm text-gray-500 mt-1">
          Cài đặt vận hành thời gian chạy. Thay đổi áp dụng ngay không cần khởi động lại. Không hiển thị biến môi trường nhạy cảm.
        </p>
      </div>

      {loading && <p className="text-sm text-gray-400">Đang tải…</p>}
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {schema && values && (
        <SettingsForm schema={schema} initialValues={values} idToken={idToken} />
      )}
    </div>
  );
}
