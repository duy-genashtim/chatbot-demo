"use client";

/**
 * Reusable button primitive — Tailwind-based, no external UI lib required.
 * Supports brand, secondary, ghost, and danger variants.
 */

import type { ButtonHTMLAttributes } from "react";

type Variant = "brand" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  brand:
    "bg-brand text-brand-foreground hover:bg-brand-hover focus-visible:ring-brand disabled:opacity-50",
  secondary:
    "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 focus-visible:ring-gray-400 disabled:opacity-50",
  ghost:
    "bg-transparent text-gray-600 hover:bg-gray-100 focus-visible:ring-gray-400 disabled:opacity-40",
  danger:
    "bg-red-600 text-white hover:bg-red-700 focus-visible:ring-red-500 disabled:opacity-50",
};

const sizeClasses: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-2.5 text-base",
};

export function Button({
  variant = "brand",
  size = "md",
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type="button"
      className={[
        "inline-flex items-center justify-center gap-2 rounded-md font-medium",
        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        variantClasses[variant],
        sizeClasses[size],
        className,
      ].join(" ")}
      {...props}
    >
      {children}
    </button>
  );
}
