"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/ui";
import { ItemStatusBadge, TaskStatusBadge } from "@/components/workspace/badges";
import { ListSkeleton } from "@/components/workspace/Shell";
import { formatDate } from "@/services/workspaceRules";
import { reviewLists } from "@/services/workspaceSelectors";
import { useWorkspace } from "@/services/workspaceStore";

export default function ReviewPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const ws = useWorkspace();
  const loaded = ws.loaded[`tasks:${orgId}`] === "ok" && ws.loaded[`items:${orgId}`] === "ok";
  const l = reviewLists(ws, orgId);
  const base = `/workspace/${orgId}`;
  if (!loaded) return <ListSkeleton rows={3} />;
  const nothing = l.tasks.length + l.items.length + l.tasksBlocked.length + l.itemsBlocked.length === 0;
  if (nothing) return <EmptyState title="Nothing waiting for your review." />;

  return (
    <div className="space-y-6" data-testid="review-page">
      <section aria-label="Evidence to review">
        <h2 className="section-title mb-2">
          Evidence to review <span className="font-normal text-ink-3 tabular-nums">{l.tasks.length}</span>
        </h2>
        {l.tasks.length === 0 ? (
          <p className="text-[14px] text-ink-3">No evidence is waiting for you.</p>
        ) : (
          <ul className="panel divide-y divide-line overflow-hidden" data-testid="review-tasks">
            {l.tasks.map(({ task, item }) => (
              <li key={task.id}>
                <Link href={`${base}/items/${item.id}#task-${task.id}`} className="flex min-h-[56px] items-center gap-3 px-4 py-2.5 hover:bg-sunken/60">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14.5px] font-semibold text-ink">{task.title}</span>
                    <span className="block truncate text-[12.5px] text-ink-3">
                      {item.obligation_title}, {task.evidence_count} file{task.evidence_count === 1 ? "" : "s"}, due {formatDate(task.due_date)}
                    </span>
                  </span>
                  <TaskStatusBadge status={task.status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Items waiting for sign-off">
        <h2 className="section-title mb-2">
          Items waiting for sign-off <span className="font-normal text-ink-3 tabular-nums">{l.items.length}</span>
        </h2>
        {l.items.length === 0 ? (
          <p className="text-[14px] text-ink-3">No items are waiting for your sign-off.</p>
        ) : (
          <ul className="panel divide-y divide-line overflow-hidden" data-testid="review-items">
            {l.items.map((item) => (
              <li key={item.id}>
                <Link href={`${base}/items/${item.id}#signoff`} className="flex min-h-[56px] items-center gap-3 px-4 py-2.5 hover:bg-sunken/60">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14.5px] font-semibold text-ink">{item.obligation_title}</span>
                    <span className="block truncate text-[12.5px] text-ink-3">
                      {item.source.reference_number}
                      {item.submitted_for_signoff_by ? `, sent by ${item.submitted_for_signoff_by.full_name}` : ""}
                    </span>
                  </span>
                  <ItemStatusBadge status={item.display_status} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {l.tasksBlocked.length + l.itemsBlocked.length > 0 && (
        <section aria-label="Waiting for another reviewer" className="opacity-80" data-testid="review-blocked">
          <h2 className="section-title mb-2">
            Waiting for another reviewer <span className="font-normal text-ink-3 tabular-nums">{l.tasksBlocked.length + l.itemsBlocked.length}</span>
          </h2>
          <p className="mb-2 text-[13.5px] text-ink-3">You worked on these, so someone else must decide.</p>
          <ul className="panel divide-y divide-line overflow-hidden bg-sunken/50">
            {l.tasksBlocked.map(({ task, item }) => (
              <li key={task.id}>
                <Link href={`${base}/items/${item.id}#task-${task.id}`} className="flex min-h-[56px] items-center gap-3 px-4 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14.5px] font-semibold text-ink-2">{task.title}</span>
                    <span className="block truncate text-[12.5px] text-ink-3">{item.obligation_title}</span>
                  </span>
                  <TaskStatusBadge status={task.status} />
                </Link>
              </li>
            ))}
            {l.itemsBlocked.map((item) => (
              <li key={item.id}>
                <Link href={`${base}/items/${item.id}#signoff`} className="flex min-h-[56px] items-center gap-3 px-4 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14.5px] font-semibold text-ink-2">{item.obligation_title}</span>
                    <span className="block truncate text-[12.5px] text-ink-3">Item sign-off</span>
                  </span>
                  <ItemStatusBadge status={item.display_status} />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
