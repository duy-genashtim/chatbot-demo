"use client";

/**
 * Landing / mode-picker page.
 *
 * Two large cards:
 *   1. Employees (HR Q&A) → Sign in with Microsoft → /chat
 *   2. General / Policy questions → Continue as guest → /ask
 *
 * Privacy notice banner displayed below cards per deploy guide.
 */

import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const PRIVACY_NOTICE =
  "Tin nhắn trò chuyện được ghi lại để cải thiện chất lượng và phân tích. " +
  "Thời gian lưu trữ: 90 ngày. Vui lòng không chia sẻ thông tin bảo mật.";

export default function LandingPage() {
  const router = useRouter();

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-3.5rem)] px-4 py-12 gap-10">
      {/* Hero heading */}
      <div className="text-center space-y-2">
        <h1 className="text-3xl font-bold text-brand">G-HelpDesk</h1>
        <p className="text-gray-500 text-sm max-w-sm">
          Chọn cách bạn muốn bắt đầu.
        </p>
      </div>

      {/* Mode picker cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 w-full max-w-2xl">
        {/* Card 1 — internal / employees */}
        <Card className="flex flex-col gap-4 hover:shadow-md transition-shadow">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-gray-900">
              Nhân viên (Hỏi đáp HR)
            </h2>
            <p className="text-sm text-gray-500">
              Hỏi về chính sách nhân sự, phúc lợi, nghỉ phép và nhiều thông tin khác.
              Cần tài khoản Microsoft công việc.
            </p>
          </div>
          <Button
            variant="brand"
            size="lg"
            className="w-full mt-auto"
            onClick={() =>
              signIn("microsoft-entra-id", { callbackUrl: "/chat" })
            }
            aria-label="Đăng nhập bằng Microsoft để truy cập Hỏi đáp HR"
          >
            Đăng nhập bằng Microsoft
          </Button>
        </Card>

        {/* Card 2 — external / guest */}
        <Card className="flex flex-col gap-4 hover:shadow-md transition-shadow">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-gray-900">
              Câu hỏi chung / Chính sách
            </h2>
            <p className="text-sm text-gray-500">
              Hỏi về chính sách và quy định công khai.
              Không cần tài khoản.
            </p>
          </div>
          <Button
            variant="secondary"
            size="lg"
            className="w-full mt-auto"
            onClick={() => router.push("/ask")}
            aria-label="Tiếp tục với tư cách khách để truy cập Hỏi đáp chính sách"
          >
            Tiếp tục với tư cách khách
          </Button>
        </Card>
      </div>

      {/* Privacy notice */}
      <div
        className="w-full max-w-2xl rounded-lg bg-brand-subtle border border-brand/20
          px-4 py-3 text-xs text-gray-600 text-center"
        role="note"
        aria-label="Thông báo về quyền riêng tư"
      >
        {PRIVACY_NOTICE}
      </div>
    </div>
  );
}
