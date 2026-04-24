/**
 * Landing route group layout — minimal wrapper with no auth guard.
 * The root layout (app/layout.tsx) already provides <html>, <body>,
 * SessionProvider, and the brand header. This layout adds nothing extra
 * so the landing page can own its full viewport height.
 */

export default function LandingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
