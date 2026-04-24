/**
 * Admin shell layout — server component.
 *
 * Guards the entire (admin) route group: redirects to "/" if the user
 * is not authenticated or does not have is_admin in their session.
 *
 * Renders a persistent sidebar with nav links and a branded header
 * with a sign-out button.
 */

import { redirect } from "next/navigation";
import Link from "next/link";
import { auth } from "@/lib/auth-config";
import { SignOutButton } from "@/components/auth/sign-out-button";
import type { EntraSession } from "@/lib/auth-config";

const NAV_LINKS = [
  { href: "/admin/documents", label: "Tài liệu" },
  { href: "/admin/settings", label: "Cài đặt" },
  { href: "/admin/admins", label: "Quản trị viên" },
  { href: "/admin/history", label: "Lịch sử" },
];

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = (await auth()) as EntraSession | null;

  // Guard: must be authenticated admin
  if (!session?.user) {
    redirect("/");
  }

  // is_admin is set in the JWT session callback (phase 02 / phase 06 extension)
  const isAdmin = (session.user as { is_admin?: boolean }).is_admin;
  if (!isAdmin) {
    redirect("/");
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Admin header */}
      <header
        className="w-full px-6 py-3 flex items-center justify-between text-white"
        style={{ backgroundColor: "var(--brand-primary, #253956)" }}
      >
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="text-lg font-semibold tracking-tight hover:opacity-80"
          >
            {process.env.NEXT_PUBLIC_BRAND_NAME ?? "G-HelpDesk"}
          </Link>
          <span className="text-brand-subtle text-sm opacity-70">/ Quản trị</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm opacity-80">{session.user.name || session.user.email}</span>
          <SignOutButton />
        </div>
      </header>

      <div className="flex flex-1">
        {/* Sidebar */}
        <nav className="w-48 bg-gray-50 border-r border-gray-200 pt-6 px-3 shrink-0">
          <ul className="space-y-1">
            {NAV_LINKS.map(({ href, label }) => (
              <li key={href}>
                <Link
                  href={href}
                  className="block px-3 py-2 rounded-md text-sm text-gray-700 hover:bg-brand-subtle hover:text-brand font-medium transition-colors"
                >
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* Main content */}
        <main className="flex-1 p-8 bg-white overflow-auto">{children}</main>
      </div>
    </div>
  );
}
