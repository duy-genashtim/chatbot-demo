"use client";

/**
 * Card primitive — simple Tailwind white card with border and shadow.
 * Accepts className for per-use overrides.
 */

import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Extra padding variant: default = "md" */
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingClasses = {
  none: "",
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};

export function Card({
  padding = "md",
  className = "",
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={[
        "bg-white rounded-xl border border-gray-200 shadow-sm",
        paddingClasses[padding],
        className,
      ].join(" ")}
      {...props}
    >
      {children}
    </div>
  );
}
