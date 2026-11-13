"use client";

import { Suspense, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Settings } from "lucide-react";
import { EmptyState, Notice, SkeletonLine } from "@/components/ui";
import AlertRow from "@/components/alerts/AlertRow";
import SignInPrompt from "@/components/alerts/SignInPrompt";
import { useSessionUser } from "@/components/workspace/Shell";
import { loadMoreAlerts, loadView, markAllRead, selectAlerts, selectView, useAlerts } from "@/services/alertsStore";

const CHIPS: { id: string; label: string; groups: string[] }[] = [
  { id: "library", label: "New circulars", groups: ["library"] },
  { id: "source_change", label: "My bank's circulars", groups: ["source_change"] },
  { id: "assigned", label: "Assigned to me", groups: ["assigned"] },
  { id: "review_waiting", label: "Waiting for me", groups: ["review_waiting"] },
  { id: "my_work_decided", label: "Decisions", groups: ["my_work_decided"] },
  { id: "deadlines", label: "Deadlines", groups: ["due_soon", "overdue"] },
  { id: "admin_queue", label: "Review queues", groups: ["admin_queue"] },
];

export default function AlertsPage() {
  return (
    <Suspense fallback={<SkeletonLine className="h-24 w-full" />}>
      <Inbox />
    </Suspense>
  );
}

function Inbox() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { user, ready, setUser } = useSessionUser();
  const s = useAlerts();
  const filter = params.get("filter") === "unread" ? "unread" : "all";
  const rawGroup = params.get("group");
  const group = CHIPS.some((c) => c.id === rawGroup) ? rawGroup : null;

  useEffect(() => {
    if (user) void loadView(filter, group);
  }, [user, filter, group]);

  if (!ready) return <SkeletonLine className="h-24 w-full" />;
  if (!user) return <SignInPrompt user={user} setUser={setUser} />;

  const go = (next: { filter?: string; group?: string | null }) => {
    const q = new URLSearchParams();
    const f = next.filter ?? filter;
    const g = next.group === undefined ? group : next.group;
    if (f === "unread") q.set("filter", "unread");
    if (g) q.set("group", g);
    const qs = q.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  // Chips only for the groups this person can have.
  const visible = s.prefs ? new Set(Object.keys(s.prefs.channels)) : null;
  const chips = CHIPS.filter((c) => (visible ? c.groups.some((g) => visible.has(g)) : c.id !== "admin_queue") || c.id === group);

  const alerts = selectAlerts(s, { filter, group });
  const view = selectView(s, filter, group);
  const loading = alerts.length === 0 && (view.status === "idle" || view.status === "loading");
  const failed = alerts.length === 0 && typeof view.status === "object";

  return (
    <div className="mx-auto max-w-[760px] space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-[22px] font-bold tracking-tight text-ink">Alerts</h1>
        <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" disabled={s.unread === 0} onClick={() => void markAllRead()}>
          Mark all read
        </button>
        <Link href="/alerts/settings" className="btn-ghost min-h-[44px] sm:min-h-0">
          <Settings className="h-4 w-4" strokeWidth={1.8} />
          Settings
        </Link>
      </div>

      <div className="space-y-3">
        <div role="tablist" aria-label="Show" className="inline-flex rounded-control border border-line-strong bg-surface p-0.5">
          {(["all", "unread"] as const).map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={filter === f}
              onClick={() => go({ filter: f })}
              className={`min-h-[44px] rounded-[5px] px-4 text-[13.5px] font-semibold transition-colors sm:min-h-[34px] ${filter === f ? "bg-accent text-accent-ink" : "text-ink-2 hover:bg-sunken"}`}
            >
              {f === "all" ? "All" : `Unread (${s.unread})`}
            </button>
          ))}
        </div>
        {chips.length > 0 && (
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0" role="group" aria-label="Kind of alert">
            {chips.map((c) => {
              const on = group === c.id;
              return (
                <button
                  key={c.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => go({ group: on ? null : c.id })}
                  className={`inline-flex min-h-[44px] shrink-0 items-center whitespace-nowrap rounded-full border px-3.5 text-[13.5px] font-semibold transition-colors sm:min-h-[36px] ${on ? "border-accent bg-accent-soft text-accent" : "border-line-strong bg-surface text-ink-2 hover:bg-sunken"}`}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {loading ? (
        <div className="panel space-y-4 p-4" aria-busy="true" aria-label="Loading">
          {[0, 1, 2, 3].map((i) => (
            <div key={i}>
              <SkeletonLine className="h-4 w-2/3" />
              <SkeletonLine className="mt-2 h-3 w-full" />
            </div>
          ))}
        </div>
      ) : failed ? (
        <Notice kind="error">
          <span>Could not load your alerts. </span>
          <button type="button" className="font-semibold underline" onClick={() => void loadView(filter, group)}>
            Try again
          </button>
        </Notice>
      ) : alerts.length === 0 ? (
        <EmptyState title={group ? "Nothing here yet." : filter === "unread" ? "No unread alerts." : "No alerts yet."}>
          {!group && filter === "all" && "You will see new circulars and work for you here."}
        </EmptyState>
      ) : (
        <div className="panel overflow-hidden">
          <ul>
            {alerts.map((a) => (
              <AlertRow key={a.id} alert={a} />
            ))}
          </ul>
        </div>
      )}

      {view.nextBefore && alerts.length > 0 && (
        <div className="flex justify-center">
          <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" disabled={view.loadingMore} onClick={() => void loadMoreAlerts(filter, group)}>
            {view.loadingMore ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-3 border-t-transparent" aria-hidden /> : null}
            Load older
          </button>
        </div>
      )}
    </div>
  );
}
