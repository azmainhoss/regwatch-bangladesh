"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/ui";
import { ListSkeleton, LoadError } from "@/components/workspace/Shell";
import { fetchAudit, type AuditRead } from "@/services/workspaceApi";
import { describeAudit, formatDateTime } from "@/services/workspaceRules";
import { userName, useWorkspace } from "@/services/workspaceStore";

export default function AuditPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const ws = useWorkspace();
  const perms = ws.me[orgId]?.permissions;
  const [events, setEvents] = useState<AuditRead[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [action, setAction] = useState("");
  const [person, setPerson] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const load = useCallback(() => {
    setError(null);
    fetchAudit(orgId, { limit: 100 })
      .then((p) => {
        setEvents(p.events);
        setNext(p.next_before);
      })
      .catch((e) => setError(e?.message || "Could not load the audit log."));
  }, [orgId]);
  useEffect(() => {
    if (perms?.view_audit_log) load();
  }, [perms?.view_audit_log, load]);

  const actions = useMemo(() => Array.from(new Set((events ?? []).map((e) => e.action))).sort(), [events]);
  const people = useMemo(() => {
    const m = new Map<string, string>();
    (events ?? []).forEach((e) => e.actor && m.set(e.actor.id, e.actor.full_name));
    return Array.from(m.entries());
  }, [events]);
  const shown = (events ?? []).filter((e) => {
    if (action && e.action !== action) return false;
    if (person && e.actor?.id !== person) return false;
    const day = e.created_at.slice(0, 10);
    if (from && day < from) return false;
    if (to && day > to) return false;
    return true;
  });

  if (!perms) return null;
  if (!perms.view_audit_log) return <EmptyState title="You do not have access to the audit log." />;
  if (error) return <LoadError message={error} onRetry={load} />;
  if (!events) return <ListSkeleton rows={5} />;
  const names = (id: string | null | undefined) => userName(ws, orgId, id);
  const entityLink = (e: AuditRead) => (e.entity_type === "compliance_item" ? `/workspace/${orgId}/items/${e.entity_id}` : null);
  const summary = (e: AuditRead) => {
    const keys = e.after && typeof e.after === "object" ? Object.keys(e.after).filter((k) => k !== "reason") : [];
    if (!keys.length) return "";
    return keys
      .slice(0, 3)
      .map((k) => `${k.replace(/_/g, " ")}: ${e.before && k in e.before ? `${String(e.before[k] ?? "none")} to ` : ""}${String(e.after[k] ?? "none").slice(0, 60)}`)
      .join("; ");
  };

  return (
    <div className="space-y-4" data-testid="audit-page">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <select className="field h-11 py-1 sm:h-9" aria-label="Action filter" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All actions</option>
          {actions.map((a) => (
            <option key={a} value={a}>
              {a.toLowerCase().replace(/_/g, " ")}
            </option>
          ))}
        </select>
        <select className="field h-11 py-1 sm:h-9" aria-label="Person filter" value={person} onChange={(e) => setPerson(e.target.value)}>
          <option value="">Everyone</option>
          {people.map(([id, n]) => (
            <option key={id} value={id}>
              {n}
            </option>
          ))}
        </select>
        <input type="date" className="field h-11 sm:h-9" aria-label="From date" value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="date" className="field h-11 sm:h-9" aria-label="To date" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      {shown.length === 0 ? (
        <EmptyState title="Nothing matches these filters." />
      ) : (
        <ol className="panel divide-y divide-line overflow-hidden">
          {shown.map((e) => {
            const link = entityLink(e);
            return (
              <li key={e.id} className="px-4 py-2.5">
                <p className="text-[14px] text-ink">{describeAudit(e, names)}</p>
                <p className="mt-0.5 text-[12.5px] text-ink-3">
                  {formatDateTime(e.created_at)}
                  {link && (
                    <>
                      {" "}
                      <Link href={link} className="font-semibold text-accent hover:underline">
                        Open item
                      </Link>
                    </>
                  )}
                </p>
                {summary(e) && <p className="mt-0.5 break-words text-[12.5px] text-ink-3">{summary(e)}</p>}
              </li>
            );
          })}
        </ol>
      )}
      {next && (
        <button
          type="button"
          className="btn-secondary min-h-[44px] sm:min-h-0"
          disabled={loadingMore}
          onClick={async () => {
            setLoadingMore(true);
            try {
              const p = await fetchAudit(orgId, { limit: 100, before: next });
              setEvents((cur) => [...(cur ?? []), ...p.events]);
              setNext(p.next_before);
            } catch (e: any) {
              setError(e?.message || "Could not load more.");
            } finally {
              setLoadingMore(false);
            }
          }}
        >
          {loadingMore ? "Loading…" : "Show older entries"}
        </button>
      )}
    </div>
  );
}
