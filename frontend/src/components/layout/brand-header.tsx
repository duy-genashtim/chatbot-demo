"use client";

/**
 * Brand header — client component.
 * Shows brand name on #253956 background.
 * Right side: if authenticated → user name + Admin link (is_admin only) + sign-out;
 *             if unauthenticated → sign-in button.
 */

import Link from "next/link";
import { signIn, signOut } from "next-auth/react";
import { useSession } from "@/hooks/use-session";

interface BrandHeaderProps {
  /** Override the sign-in callback URL. Defaults to "/chat". */
  signInCallbackUrl?: string;
}

export function BrandHeader({ signInCallbackUrl = "/chat" }: BrandHeaderProps) {
  const { session, isAdmin, status } = useSession();
  const isAuthenticated = status === "authenticated";

  return (
    <header
      className="w-full bg-brand text-brand-foreground px-4 md:px-6 py-3
        flex items-center justify-between gap-3 shrink-0"
      style={{ backgroundColor: "var(--brand-primary)" }}
    >
      {/* Brand name */}
      <Link
        href="/"
        className="text-lg font-semibold tracking-tight text-white hover:opacity-80 transition-opacity"
        aria-label="Trang chủ G-HelpDesk"
      >
        {process.env.NEXT_PUBLIC_BRAND_NAME ?? "G-HelpDesk"}
      </Link>

      {/* Right-side controls */}
      <div className="flex items-center gap-3 text-sm">
        {status === "loading" ? (
          <span className="opacity-50 text-xs">Đang tải…</span>
        ) : isAuthenticated ? (
          <>
            {/* User name */}
            {session?.user?.name && (
              <span className="hidden sm:inline opacity-80 max-w-[140px] truncate">
                {session.user.name}
              </span>
            )}

            {/* Admin link — only when is_admin */}
            {isAdmin && (
              <Link
                href="/admin/documents"
                className="opacity-80 hover:opacity-100 hover:underline transition-opacity"
                aria-label="Bảng quản trị"
              >
                Quản trị
              </Link>
            )}

            {/* Sign-out */}
            <button
              type="button"
              onClick={() => signOut({ callbackUrl: "/" })}
              className="px-3 py-1 rounded-md border border-white/30 text-white text-xs
                hover:bg-white/10 transition-colors"
              aria-label="Đăng xuất"
            >
              Đăng xuất
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() =>
              signIn("microsoft-entra-id", { callbackUrl: signInCallbackUrl })
            }
            className="px-3 py-1 rounded-md border border-white/30 text-white text-xs
              hover:bg-white/10 transition-colors"
            aria-label="Đăng nhập bằng Microsoft"
          >
            Đăng nhập
          </button>
        )}
      </div>
    </header>
  );
}
