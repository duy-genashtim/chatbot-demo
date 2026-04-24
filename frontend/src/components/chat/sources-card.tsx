"use client";

/**
 * Sources card — displayed above the current assistant bubble when a
 * "sources" SSE event arrives (before the first delta token).
 * Shows each source as a small chip: "{source} · {section}".
 */

import type { Source } from "@/hooks/use-chat-stream";

interface SourcesCardProps {
  sources: Source[];
}

export function SourcesCard({ sources }: SourcesCardProps) {
  if (sources.length === 0) return null;

  return (
    <div
      className="flex flex-wrap gap-2 px-1 py-2"
      aria-label="Tài liệu tham chiếu"
    >
      {sources.map((s, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full
            text-xs font-medium bg-brand-subtle text-brand border border-brand/20"
          title={s.section ? `${s.source} — ${s.section}` : s.source}
        >
          <span className="max-w-[140px] truncate">{s.source}</span>
          {s.section && (
            <>
              <span className="opacity-50">·</span>
              <span className="max-w-[100px] truncate opacity-75">{s.section}</span>
            </>
          )}
        </span>
      ))}
    </div>
  );
}
