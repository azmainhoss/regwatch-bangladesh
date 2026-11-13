"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Tag } from "../StatusBadge";
import { reviewCounts } from "@/services/workspaceSelectors";
import { useWorkspace } from "@/services/workspaceStore";

/** The tabs of a bank workspace. On phones they scroll inside their own strip. */
export default function WorkspaceNav({ orgId }: { orgId: string }) {
  const ws = useWorkspace();
  const pathname = usePathname();
  const perms = ws.me[orgId]?.permissions;
  const counts = reviewCounts(ws, orgId);
  const base = `/workspace/${orgId}`;
  const tabs = [
    { href: base, label: "Dashboard", exact: true, show: true },
    { href: `${base}/registers`, label: "Registers", show: true },
    { href: `${base}/tasks`, label: "Tasks", show: true },
    { href: `${base}/review`, label: "Review", show: true, badge: counts.total },
    { href: `${base}/report`, label: "Report", show: true },
    { href: `${base}/settings`, label: "Settings", show: !!perms && (perms.manage_members || perms.manage_departments) },
    { href: `${base}/audit`, label: "Audit log", show: !!perms?.view_audit_log },
  ].filter((t) => t.show);
  return (
    <nav aria-label="Workspace" className="-mx-4 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0" data-testid="workspace-nav">
      <ul className="flex min-w-max gap-1">
        {tabs.map((t) => {
          const active = t.exact ? pathname === t.href : pathname.startsWith(t.href);
          return (
            <li key={t.href}>
              <Link
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-[44px] items-center gap-1.5 whitespace-nowrap border-b-2 px-3 text-[14px] font-semibold transition-colors ${
                  active ? "border-accent text-ink" : "border-transparent text-ink-3 hover:text-ink"
                }`}
              >
                {t.label}
                {!!t.badge && (
                  <span data-testid="review-badge">
                    <Tag tone="warn">{t.badge}</Tag>
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
