import type { Metadata } from "next";
import "@/styles/globals.css";
import { SessionProvider } from "@/components/auth/session-provider";
import { auth } from "@/lib/auth-config";

export const metadata: Metadata = {
  title: "G-HelpDesk",
  description: "Chatbot RAG hai miền — HR nội bộ và chính sách công khai",
};

/**
 * Root layout — provides html/body shell and SessionProvider only.
 * Each route group ((landing), (app), (admin)) owns its own header/layout.
 *
 * We fetch the session on the server via auth() and forward it to
 * SessionProvider so useSession() starts with the same status on both
 * the SSR pass and the initial client hydration — otherwise
 * brand-header renders "Loading…" on the server but "authenticated"
 * on the client, causing React hydration warnings.
 *
 * suppressHydrationWarning on <body> neutralises attribute mismatches
 * injected by browser extensions (e.g. dark-mode toggles, password
 * managers) that run before React hydrates.
 */
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  return (
    // suppressHydrationWarning on <html>: browser extensions (dark-mode,
    // MDL, translator, Grammarly, etc.) inject classes/attributes onto
    // <html> or <body> before React hydrates. Without this flag React
    // aborts hydration and downgrades the whole page to CSR, showing the
    // red "tree hydrated but attributes didn't match" overlay.
    <html lang="en" suppressHydrationWarning>
      <body
        className="bg-white text-gray-900 antialiased"
        suppressHydrationWarning
      >
        {/* SessionProvider makes useSession() available in all client components */}
        <SessionProvider session={session}>{children}</SessionProvider>
      </body>
    </html>
  );
}
