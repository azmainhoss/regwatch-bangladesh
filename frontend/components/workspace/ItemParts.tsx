"use client";

import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import ReasonModal from "./ReasonModal";
import type { ItemRead, ItemReviewRead, TaskRead } from "@/services/workspaceApi";
import {
  Me,
  SELF_REVIEW_ITEM,
  canAcknowledge,
  canExemptOrReopen,
  canSignOffRole,
  describeAudit,
  formatDateTime,
  signoffBlock,
} from "@/services/workspaceRules";
import { acknowledgeSourceChange, loadHistory, moveItem, signOffItem, useWorkspace, userName } from "@/services/workspaceStore";

// ------------------------------------------------------------------------------------ circular changed
export function SourceChangeBanner({ orgId, item, me, onAddFromNewer }: { orgId: string; item: ItemRead; me: Me; onAddFromNewer: (documentId: string) => void }) {
  const [marking, setMarking] = useState(false);
  const [exempting, setExempting] = useState(false);
  const [reopening, setReopening] = useState(false);
  const change = item.source_change;
  if (!change) return null;
  const ref = change.by?.reference_number || change.by?.title || "the newer circular";
  const newerId = change.by?.id ?? (change.kind === "NEW_VERSION" ? item.source.document_id : null);
  const canAck = canAcknowledge(me);
  const canExempt = canExemptOrReopen(me) && item.status !== "COMPLIANT" && item.status !== "EXEMPTED";
  const canReopen = canExemptOrReopen(me) && item.status === "COMPLIANT";
  return (
    <div role="alert" data-testid="source-change-banner" className="rounded-panel border border-warn/40 bg-warn-soft px-4 py-3.5">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" strokeWidth={2} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-[14.5px] font-semibold text-ink">Circular changed</p>
          <p className="mt-0.5 text-[14px] text-ink-2">{change.detail} This item has not been changed. A person needs to decide what it means for the bank.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {canAck && (
              <button type="button" className="btn-primary min-h-[44px] sm:min-h-0" onClick={() => setMarking(true)}>
                Mark as reviewed
              </button>
            )}
            {newerId && canAcknowledge(me) && (
              <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => onAddFromNewer(newerId)}>
                Add items from {change.by ? ref : "the new version"}
              </button>
            )}
            {canExempt && (
              <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => setExempting(true)}>
                Exempt this item
              </button>
            )}
            {canReopen && (
              <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => setReopening(true)}>
                Reopen
              </button>
            )}
          </div>
        </div>
      </div>
      <ReasonModal open={marking} onClose={() => setMarking(false)} title="Mark as reviewed" subtitle="Say what you decided, for the record." label="Note" confirmLabel="Mark as reviewed" onConfirm={(note) => void acknowledgeSourceChange(orgId, item.id, note)} />
      <ReasonModal open={exempting} onClose={() => setExempting(false)} title="Exempt this item" initial={change.by ? `Replaced by ${ref}` : ""} confirmLabel="Exempt" onConfirm={(r) => void moveItem(orgId, item.id, "EXEMPTED", r)} />
      <ReasonModal open={reopening} onClose={() => setReopening(false)} title="Reopen this item" confirmLabel="Reopen" onConfirm={(r) => void moveItem(orgId, item.id, "REOPEN", r)} />
    </div>
  );
}

// ------------------------------------------------------------------------------------ sign-off
export function SignoffBox({ orgId, item, me, tasks, reviews }: { orgId: string; item: ItemRead; me: Me; tasks: TaskRead[]; reviews: ItemReviewRead[] }) {
  const [comments, setComments] = useState("");
  const [sendingBack, setSendingBack] = useState(false);
  const waiting = item.status === "EVIDENCE_SUBMITTED";
  const role = canSignOffRole(me);
  const block = signoffBlock(me, item, tasks);
  const visible = waiting || reviews.length > 0;
  // A link ending in #signoff (from the Review list) scrolls here once the box is on screen.
  useEffect(() => {
    if (visible && typeof window !== "undefined" && window.location.hash === "#signoff") {
      setTimeout(() => document.getElementById("signoff")?.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
    }
  }, [visible]);
  if (!visible) return null;
  return (
    <section id="signoff" aria-label="Sign-off" data-testid="signoff-box" className="space-y-3">
      {waiting && (
        <div className="rounded-panel border border-warn/30 bg-warn-soft px-4 py-3.5">
          <p className="text-[14.5px] font-semibold text-ink">Waiting for sign-off</p>
          <p className="mt-0.5 text-[13.5px] text-ink-2">
            {item.submitted_for_signoff_by ? `Sent by ${item.submitted_for_signoff_by.full_name}` : "Sent for sign-off"}
            {item.submitted_for_signoff_at ? `, ${formatDateTime(item.submitted_for_signoff_at)}` : ""}.
          </p>
          {role &&
            (block ? (
              <p className="mt-2 text-[13.5px] text-ink-2" data-testid="self-signoff-note">
                {block || SELF_REVIEW_ITEM}
              </p>
            ) : (
              <>
                <textarea className="field mt-2 min-h-[64px]" placeholder="Comment (needed to send it back)" aria-label="Sign-off comment" value={comments} onChange={(e) => setComments(e.target.value)} maxLength={2000} />
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn-primary min-h-[44px] sm:min-h-0"
                    onClick={() => {
                      void signOffItem(orgId, item.id, "APPROVED", comments.trim());
                      setComments("");
                    }}
                  >
                    Approve as compliant
                  </button>
                  <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => setSendingBack(true)}>
                    Send back
                  </button>
                </div>
              </>
            ))}
        </div>
      )}
      {reviews.length > 0 && (
        <ul className="space-y-1.5" aria-label="Past sign-offs">
          {reviews.map((r) => (
            <li key={r.id} className="rounded-control bg-sunken/60 px-3 py-2 text-[13.5px]">
              <span className="font-semibold text-ink">{r.decision === "APPROVED" ? "Signed off" : "Sent back"}</span>{" "}
              <span className="text-ink-3">
                by {r.reviewer.full_name}, {formatDateTime(r.created_at)}
              </span>
              {r.comments && <p className="mt-0.5 text-ink-2">{r.comments}</p>}
            </li>
          ))}
        </ul>
      )}
      <ReasonModal open={sendingBack} onClose={() => setSendingBack(false)} title="Send this item back" label="Comment" confirmLabel="Send back" initial={comments} onConfirm={(t) => { void signOffItem(orgId, item.id, "REJECTED", t); setComments(""); }} />
    </section>
  );
}

// ------------------------------------------------------------------------------------ history
export function HistoryList({ orgId, itemId }: { orgId: string; itemId: string }) {
  const ws = useWorkspace();
  const events = ws.history[itemId];
  const next = ws.historyNext[itemId];
  useEffect(() => {
    void loadHistory(orgId, itemId);
  }, [orgId, itemId]);
  const names = (id: string | null | undefined) => userName(ws, orgId, id);
  return (
    <section aria-label="History" data-testid="history-list">
      <h3 className="section-title mb-3">History</h3>
      {!events ? (
        <p className="text-[14px] text-ink-3">Loading history…</p>
      ) : events.length === 0 ? (
        <p className="text-[14px] text-ink-3">Nothing has happened to this item yet.</p>
      ) : (
        <ol className="divide-y divide-line rounded-panel border border-line">
          {events.map((e) => (
            <li key={e.id} className={`px-3.5 py-2.5 ${e.id.startsWith("tmp:") ? "opacity-70" : ""}`}>
              <p className="text-[14px] text-ink">{describeAudit(e, names)}</p>
              <p className="mt-0.5 text-[12.5px] text-ink-3">{formatDateTime(e.created_at)}</p>
            </li>
          ))}
        </ol>
      )}
      {next && (
        <button type="button" className="btn-secondary mt-3 min-h-[44px] sm:min-h-0" onClick={() => void loadHistory(orgId, itemId, true)}>
          Show more
        </button>
      )}
    </section>
  );
}
