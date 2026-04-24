/**
 * (app) route group layout — wraps /chat and /ask with the BrandHeader.
 * SessionProvider is already in the root layout; no need to re-wrap.
 * Auth gating is handled per-page (chat requires auth, ask does not).
 */

import { BrandHeader } from "@/components/layout/brand-header";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <BrandHeader />
      <main className="flex-1 min-h-0 overflow-hidden">{children}</main>
    </div>
  );
}
