import type { Metadata } from "next";

// The library app: useful to people, but its content lives on the circular pages, which are the ones to index.
export const metadata: Metadata = {
  title: "Library | Amar Circular",
  robots: { index: false, follow: true },
  alternates: { canonical: "/dashboard" },
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return children;
}
