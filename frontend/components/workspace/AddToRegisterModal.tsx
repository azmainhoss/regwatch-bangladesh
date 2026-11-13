"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { Modal, ModalHeader, Notice, hasBangla } from "../ui";
import { Tag } from "../StatusBadge";
import { searchCirculars, type SearchHit } from "@/services/api";
import { fetchAddable, type AddableObligations, type MyOrg } from "@/services/workspaceApi";
import { formatDate } from "@/services/workspaceRules";
import { addObligations, ensureWorkspace, orgRegisters, setNotice, useWorkspace } from "@/services/workspaceStore";

const FORCE_WORD: Record<string, string> = { AMENDED: "amended", REPLACED: "replaced", REPEALED: "repealed" };

/**
 * Adds checked obligations of a circular to a register (or to a new register named after it).
 * Used on the register screen (register fixed) and on the circular screen (register chosen here).
 */
export default function AddToRegisterModal({
  open,
  onClose,
  orgId,
  orgOptions,
  onOrgChange,
  registerId,
  initialDocumentId,
  onAdded,
}: {
  open: boolean;
  onClose: () => void;
  orgId: string;
  orgOptions?: MyOrg[];
  onOrgChange?: (id: string) => void;
  registerId?: string | null;
  initialDocumentId?: string | null;
  onAdded?: (registerId: string, count: number, skipped: number) => void;
}) {
  const id = useId();
  const ws = useWorkspace();
  const registers = orgRegisters(ws, orgId);
  const [docId, setDocId] = useState<string | null>(initialDocumentId ?? null);
  const [term, setTerm] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [data, setData] = useState<AddableObligations | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<string>(registerId ?? "NEW");
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const searchSeq = useRef(0);

  useEffect(() => {
    if (!open) return;
    setDocId(initialDocumentId ?? null);
    setTerm("");
    setHits(null);
    setData(null);
    setError(null);
    setSelected({});
    setTarget(registerId ?? (registers[0]?.id ?? "NEW"));
    void ensureWorkspace(orgId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialDocumentId, registerId, orgId]);

  // Search circulars (the same search the Search page uses).
  useEffect(() => {
    if (!open || docId || term.trim().length < 2) {
      if (!docId) setHits(null);
      return;
    }
    const seq = ++searchSeq.current;
    setSearching(true);
    const t = window.setTimeout(async () => {
      try {
        const r = await searchCirculars({ q: term.trim(), limit: 8 });
        if (seq === searchSeq.current) setHits(r.results.filter((h) => !h.is_private));
      } catch {
        if (seq === searchSeq.current) setHits([]);
      } finally {
        if (seq === searchSeq.current) setSearching(false);
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [term, docId, open]);

  // The obligations of the chosen circular.
  useEffect(() => {
    if (!open || !docId) {
      setData(null);
      return;
    }
    let alive = true;
    setLoading(true);
    setError(null);
    fetchAddable(orgId, docId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e?.message || "Could not load this circular."))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [open, docId, orgId]);

  const chosenRegister = target !== "NEW" ? target : null;
  const rows = useMemo(
    () =>
      (data?.obligations ?? []).map((o) => {
        const already = !!chosenRegister && o.already_in_register_ids.includes(chosenRegister);
        return { o, already, disabled: !o.addable || already, reason: already ? "Already in this register" : o.reason_not_addable };
      }),
    [data, chosenRegister]
  );

  // Preselect everything that can be added whenever the list or the register changes.
  useEffect(() => {
    const next: Record<string, boolean> = {};
    rows.forEach((r) => (next[r.o.id] = !r.disabled));
    setSelected(next);
  }, [rows]);

  const addable = rows.filter((r) => !r.disabled);
  const picked = addable.filter((r) => selected[r.o.id]);
  const allOn = addable.length > 0 && picked.length === addable.length;
  const doc = data?.document;
  const notInForce = doc && doc.in_force_status !== "IN_FORCE";

  const submit = async () => {
    if (!doc || picked.length === 0) return;
    const source = { documentId: doc.id, reference: doc.reference_number, title: doc.title, publicationDate: null, versionId: doc.current_version_id };
    const chosen = picked.map((r) => r.o);
    const newTitle = `${doc.reference_number || "Circular"}: ${doc.title}`.slice(0, 255);
    onClose();
    const res = await addObligations(orgId, chosenRegister ? { registerId: chosenRegister } : { newTitle }, source, chosen);
    if (!res) return;
    const skippedText = res.skipped.length ? ` ${res.skipped.length} skipped: ${Array.from(new Set(res.skipped.map((s) => s.reason))).join(", ")}.` : "";
    setNotice({ kind: res.skipped.length ? "info" : "success", text: `${chosen.length - res.skipped.length} item${chosen.length - res.skipped.length === 1 ? "" : "s"} added to the register.${skippedText}` });
    onAdded?.(res.registerId, chosen.length - res.skipped.length, res.skipped.length);
  };

  return (
    <Modal open={open} onClose={onClose} labelledBy={`${id}-title`} width="max-w-2xl">
      <ModalHeader id={`${id}-title`} title="Add to a register" subtitle={doc ? `${doc.reference_number ?? ""} ${doc.title}`.trim() : "Pick a circular, then the obligations to track"} onClose={onClose} />
      <div className="max-h-[72dvh] space-y-4 overflow-y-auto px-5 py-4">
        {orgOptions && orgOptions.length > 1 && !registerId && (
          <div>
            <label className="field-label" htmlFor={`${id}-org`}>
              Bank workspace
            </label>
            <select id={`${id}-org`} className="field h-11 py-1 sm:h-9" value={orgId} onChange={(e) => onOrgChange?.(e.target.value)}>
              {orgOptions.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {!docId && (
          <div>
            <label className="field-label" htmlFor={`${id}-q`}>
              Find a circular
            </label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" />
              <input id={`${id}-q`} className="field h-11 pl-8 sm:h-9" placeholder="Reference number or words from the title" value={term} onChange={(e) => setTerm(e.target.value)} />
            </div>
            {searching && <p className="mt-2 text-[13px] text-ink-3">Searching…</p>}
            {hits && hits.length === 0 && !searching && <p className="mt-2 text-[13.5px] text-ink-3">No circulars found.</p>}
            {hits && hits.length > 0 && (
              <ul className="mt-2 divide-y divide-line rounded-control border border-line">
                {hits.map((h) => (
                  <li key={h.document_id}>
                    <button type="button" className="flex min-h-[48px] w-full flex-col items-start px-3 py-2 text-left hover:bg-sunken" onClick={() => setDocId(h.document_id)}>
                      <span className="text-[13px] font-semibold tabular-nums text-accent">{h.reference_number || "Circular"}</span>
                      <span className="text-[14px] text-ink" lang={hasBangla(h.title) ? "bn" : undefined}>
                        {h.title}
                      </span>
                      <span className="text-[12.5px] text-ink-3">{formatDate(h.publication_date)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {docId && loading && <p className="text-[14px] text-ink-3">Loading the checked obligations…</p>}
        {error && <Notice kind="error">{error}</Notice>}

        {doc && notInForce && (
          <Notice kind="warning">
            <span>
              This circular was {FORCE_WORD[doc.in_force_status] ?? "changed"}
              {doc.in_force_by ? ` by ${doc.in_force_by.reference_number || doc.in_force_by.title}` : ""}.
            </span>
            {doc.in_force_by && (
              <span className="mt-2 flex flex-wrap gap-2">
                <Link href={`/?doc=${doc.in_force_by.id}`} className="btn-secondary min-h-[44px] sm:min-h-0">
                  Open {doc.in_force_by.reference_number || "it"}
                </Link>
                <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => setDocId(doc.in_force_by!.id)}>
                  Add from {doc.in_force_by.reference_number || "it"} instead
                </button>
              </span>
            )}
          </Notice>
        )}

        {doc && (
          <>
            {!registerId && (
              <div>
                <label className="field-label" htmlFor={`${id}-reg`}>
                  Register
                </label>
                <select id={`${id}-reg`} className="field h-11 py-1 sm:h-9" value={target} onChange={(e) => setTarget(e.target.value)}>
                  <option value="NEW">New register named after this circular</option>
                  {registers.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {data && data.obligations.length === 0 ? (
              <p className="rounded-panel border border-dashed border-line-strong px-4 py-6 text-center text-[14px] text-ink-3">
                This circular has no checked obligations yet. Obligations appear here after their quotes are checked.
              </p>
            ) : (
              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <label className="flex min-h-[44px] items-center gap-2 text-[13.5px] font-semibold text-ink-2 sm:min-h-0">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-[rgb(var(--accent))]"
                      checked={allOn}
                      disabled={addable.length === 0}
                      onChange={(e) => {
                        const next: Record<string, boolean> = {};
                        rows.forEach((r) => (next[r.o.id] = !r.disabled && e.target.checked));
                        setSelected(next);
                      }}
                    />
                    Select all addable
                  </label>
                  <span className="text-[13px] text-ink-3 tabular-nums">
                    {picked.length} of {rows.length}
                  </span>
                </div>
                <ul className="divide-y divide-line rounded-control border border-line" data-testid="addable-list">
                  {rows.map(({ o, disabled, reason }) => (
                    <li key={o.id} className={`flex gap-3 px-3 py-3 ${disabled ? "opacity-70" : ""}`}>
                      <input
                        type="checkbox"
                        aria-label={`Add ${o.title}`}
                        className="mt-1 h-4 w-4 shrink-0 accent-[rgb(var(--accent))]"
                        checked={!!selected[o.id]}
                        disabled={disabled}
                        onChange={(e) => setSelected((s) => ({ ...s, [o.id]: e.target.checked }))}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="text-[14.5px] font-semibold text-ink">{o.title}</span>
                          <Tag tone="accent">{o.obligation_type.charAt(0) + o.obligation_type.slice(1).toLowerCase().replace(/_/g, " ")}</Tag>
                          {o.page_number && <span className="text-[12.5px] tabular-nums text-ink-3">page {o.page_number}</span>}
                        </div>
                        <p className={`mt-1 text-[13.5px] text-ink-2 ${expanded[o.id] ? "" : "line-clamp-2"}`} lang={hasBangla(o.quote) ? "bn" : undefined}>
                          &ldquo;{o.quote}&rdquo;
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-x-3 text-[12.5px] text-ink-3">
                          <button type="button" className="min-h-[32px] font-semibold text-accent" onClick={() => setExpanded((x) => ({ ...x, [o.id]: !x[o.id] }))}>
                            {expanded[o.id] ? "Show less" : "Show all"}
                          </button>
                          {o.regulatory_deadline && <span className="font-semibold text-warn">Deadline {formatDate(o.regulatory_deadline)}</span>}
                          {reason && <span className="font-semibold text-ink-2">{reason}</span>}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-line px-5 py-3">
        {docId && !initialDocumentId ? (
          <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={() => { setDocId(null); setData(null); }}>
            Pick another circular
          </button>
        ) : (
          <span />
        )}
        <div className="flex gap-2">
          <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-primary min-h-[44px] sm:min-h-0" disabled={picked.length === 0} onClick={submit} data-testid="add-items-confirm">
            Add {picked.length} item{picked.length === 1 ? "" : "s"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
