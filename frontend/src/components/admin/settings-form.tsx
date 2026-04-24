"use client";

/**
 * Schema-driven settings form.
 *
 * Renders one input per whitelisted setting key based on type:
 *   string   → <input type="text">
 *   number   → <input type="number" step="any">
 *   integer  → <input type="number" step="1">
 *   boolean  → <input type="checkbox">
 *   text     → <textarea>
 *
 * Only sends keys that actually changed to PUT /api/admin/settings.
 */

import { useState, useEffect } from "react";
import {
  adminApi,
  SettingsSchemaMap,
  SettingsValuesMap,
} from "@/lib/admin-api";
import { ApiError } from "@/lib/api-client";

interface Props {
  schema: SettingsSchemaMap;
  initialValues: SettingsValuesMap;
  idToken: string | undefined;
}

export function SettingsForm({ schema, initialValues, idToken }: Props) {
  const [values, setValues] = useState<SettingsValuesMap>({ ...initialValues });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  // Domains whose Gemini context cache the backend dropped on the last save.
  // Surfaced as a small toast so the admin knows the next chat reply will be
  // briefly slower while the cache rebuilds.
  const [cacheRebuildDomains, setCacheRebuildDomains] = useState<string[]>([]);

  // Reset local state when parent refreshes values
  useEffect(() => {
    setValues({ ...initialValues });
  }, [initialValues]);

  function handleChange(key: string, raw: string | boolean) {
    setValues((prev) => ({ ...prev, [key]: raw }));
    setSaved(false);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    setCacheRebuildDomains([]);

    // Only send changed values
    const changed: SettingsValuesMap = {};
    for (const key of Object.keys(schema)) {
      if (String(values[key]) !== String(initialValues[key])) {
        changed[key] = values[key];
      }
    }
    if (Object.keys(changed).length === 0) {
      setSaved(true);
      return;
    }

    setSaving(true);
    try {
      const result = await adminApi.updateSettings(changed, idToken);
      setSaved(true);
      if (result.cache_rebuild_pending?.length) {
        setCacheRebuildDomains(result.cache_rebuild_pending);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Lưu thất bại.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSave} className="space-y-5">
      {Object.entries(schema).map(([key, meta]) => {
        const currentVal = values[key] ?? meta.default;
        return (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">
              {meta.label}
              <span className="ml-2 text-xs text-gray-400 font-normal">{key}</span>
            </label>

            {meta.type === "boolean" ? (
              <input
                type="checkbox"
                checked={Boolean(currentVal)}
                onChange={(e) => handleChange(key, e.target.checked)}
                className="w-4 h-4"
              />
            ) : meta.type === "text" ? (
              <textarea
                value={String(currentVal ?? "")}
                onChange={(e) => handleChange(key, e.target.value)}
                rows={6}
                className="border rounded px-2 py-1 text-sm font-mono resize-y w-full max-w-2xl min-h-[8rem]"
                placeholder="Văn bản thuần hoặc markdown — hiển thị trong câu trả lời của trợ lý."
              />
            ) : meta.type === "string" ? (
              <input
                type="text"
                value={String(currentVal ?? "")}
                onChange={(e) => handleChange(key, e.target.value)}
                className="border rounded px-2 py-1 text-sm w-64"
              />
            ) : (
              <input
                type="number"
                step={meta.type === "number" ? "any" : "1"}
                min={meta.min}
                max={meta.max}
                value={Number(currentVal)}
                onChange={(e) => handleChange(key, e.target.value)}
                className="border rounded px-2 py-1 text-sm w-48"
              />
            )}

            {(meta.min !== undefined || meta.max !== undefined) && (
              <span className="text-xs text-gray-400">
                {meta.min !== undefined && `tối thiểu ${meta.min}`}
                {meta.min !== undefined && meta.max !== undefined && " / "}
                {meta.max !== undefined && `tối đa ${meta.max}`}
              </span>
            )}
          </div>
        );
      })}

      {error && <p className="text-red-600 text-sm">{error}</p>}
      {saved && <p className="text-green-600 text-sm">Đã lưu cài đặt.</p>}
      {cacheRebuildDomains.length > 0 && (
        <div
          role="status"
          className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
        >
          <strong>Lưu ý:</strong> Đã xóa cache ngữ cảnh Gemini cho{" "}
          <code>{cacheRebuildDomains.join(", ")}</code>. Câu trả lời đầu tiên
          của miền này sẽ chậm hơn trong lúc cache được dựng lại với system
          instruction mới.
        </div>
      )}

      <button
        type="submit"
        disabled={saving}
        className="px-5 py-2 rounded text-sm font-medium text-white disabled:opacity-50"
        style={{ backgroundColor: "var(--brand-primary, #253956)" }}
      >
        {saving ? "Đang lưu…" : "Lưu cài đặt"}
      </button>
    </form>
  );
}
