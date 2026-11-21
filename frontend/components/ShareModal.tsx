"use client";

import { useEffect, useId, useState } from "react";
import { Check, Download, Loader2, Mail, UserPlus } from "lucide-react";
import type { AuthUser, DocumentItem } from "@/services/api";
import { assign, downloadEmailFile, fetchTeam, sendEmail, type TeamMember } from "@/services/shareApi";
import { addAssignments } from "@/services/assignmentsStore";
import { mindMapPng, type MindBranch } from "./MindMap";
import { Modal, ModalHeader, Notice } from "./ui";

// The team list is loaded once per tab and kept, so the dialog opens with names already there.
let teamCache: TeamMember[] | null = null;
let teamLoad: Promise<TeamMember[]> | null = null;
function loadTeam() {
  if (!teamLoad) teamLoad = fetchTeam().then((t) => (teamCache = t)).catch((e) => ((teamLoad = null), Promise.reject(e)));
  return teamLoad;
}

const EMAIL_RE = /^[^\s@,;]+@[^\s@,;]+\.[^\s@,;]+$/;

/**
 * Two jobs in one dialog:
 * - Email: send the circular's checked summary, what banks must do, key dates and its mind map, with the
 *   original PDF attached. If this server has no mail set up, the same email downloads as a draft file.
 * - Assign to team: pick colleagues from your bank; it appears on their dashboard and they get the email.
 */
export default function ShareModal({
  mode,
  doc,
  branches,
  currentUser,
  onClose,
  onSwitch,
}: {
  mode: "email" | "assign";
  doc: DocumentItem;
  branches: MindBranch[];
  currentUser: AuthUser | null;
  onClose: () => void;
  onSwitch: (m: "email" | "assign") => void;
}) {
  const id = useId();
  const [team, setTeam] = useState<TeamMember[] | null>(teamCache);
  const [teamError, setTeamError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ kind: "success" | "error" | "info"; text: string } | null>(null);
  const [needFile, setNeedFile] = useState(false);

  useEffect(() => {
    loadTeam()
      .then(setTeam)
      .catch((e) => setTeamError(e?.message || "Could not load your team."));
  }, []);

  const others = (team ?? []).filter((m) => m.user_id !== currentUser?.id);
  const typed = to
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const badTyped = typed.filter((t) => !EMAIL_RE.test(t));
  const recipients = Array.from(new Set([...typed, ...others.filter((m) => picked.includes(m.user_id)).map((m) => m.email)]));
  const fileName = `${(doc.reference_number || "circular").replace(/[^\w.-]+/g, "-")}.eml`;

  const toggle = (uid: string) => setPicked((p) => (p.includes(uid) ? p.filter((x) => x !== uid) : [...p, uid]));

  const picture = async () => {
    try {
      return await mindMapPng(doc, branches);
    } catch {
      return null;
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setResult(null);
    setBusy(true);
    try {
      const png = await picture();
      if (mode === "email") {
        if (recipients.length === 0 || badTyped.length > 0) return;
        try {
          const r = await sendEmail({ document_id: doc.id, to: recipients, note: note.trim() || undefined, mind_map_png: png });
          setResult({ kind: "success", text: r.message });
        } catch (err: any) {
          if (err?.status === 409) {
            setNeedFile(true);
            setResult({ kind: "info", text: "Email is not set up on this server yet. Download the email below and send it from your own mail app." });
          } else throw err;
        }
      } else {
        if (picked.length === 0) return;
        const r = await assign({ document_id: doc.id, assignee_user_ids: picked, note: note.trim() || undefined, due_date: due || null, send_email: true, mind_map_png: png });
        addAssignments(r.assignments);
        const names = r.assignments.map((a) => a.assignee_name).join(", ");
        setResult({
          kind: "success",
          text: `Assigned to ${names}. It is on their dashboard now${r.emailed ? " and they have the email" : r.email_off ? " (email is not set up on this server yet)" : ""}.`,
        });
        setPicked([]);
      }
    } catch (err: any) {
      setResult({ kind: "error", text: err?.message || "That did not work. Please try again." });
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    setBusy(true);
    try {
      await downloadEmailFile({ document_id: doc.id, to: recipients, note: note.trim() || undefined, mind_map_png: await picture() }, fileName);
      setResult({ kind: "success", text: "Downloaded. Open the file: it opens in your mail app as a draft with the PDF attached." });
    } catch (err: any) {
      setResult({ kind: "error", text: err?.message || "Could not make the email file." });
    } finally {
      setBusy(false);
    }
  };

  const canSend = mode === "email" ? recipients.length > 0 && badTyped.length === 0 : picked.length > 0;

  return (
    <Modal open onClose={onClose} labelledBy={`${id}-title`} width="max-w-lg">
      <ModalHeader
        id={`${id}-title`}
        title={mode === "email" ? "Email this circular" : "Assign to your team"}
        subtitle={doc.reference_number || doc.title}
        onClose={onClose}
      />
      <div className="px-5 pt-3">
        <div role="tablist" className="inline-flex rounded-control bg-sunken p-0.5">
          {(
            [
              { id: "assign", label: "Assign", Icon: UserPlus },
              { id: "email", label: "Email", Icon: Mail },
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={mode === t.id}
              onClick={() => {
                setResult(null);
                setNeedFile(false);
                onSwitch(t.id);
              }}
              className={`inline-flex items-center gap-1.5 rounded-[7px] px-3 py-1.5 text-[13.5px] font-semibold ${mode === t.id ? "bg-surface text-ink shadow-sm" : "text-ink-3 hover:text-ink"}`}
            >
              <t.Icon className="h-3.5 w-3.5" /> {t.label}
            </button>
          ))}
        </div>
      </div>
      <form onSubmit={submit} className="space-y-4 px-5 py-4">
        <div>
          <p className="field-label">{mode === "email" ? "Your team (tap to add)" : "Who should handle it"}</p>
          {team === null && !teamError ? (
            <p className="flex items-center gap-2 text-[13.5px] text-ink-3">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading your team...
            </p>
          ) : others.length === 0 ? (
            <p className="text-[13.5px] text-ink-3">
              {teamError || (mode === "assign" ? "Nobody else is in your bank's workspace yet. Add people under Workspace, Settings." : "Nobody else in your workspace yet. Type email addresses below.")}
            </p>
          ) : (
            <ul className="max-h-48 space-y-1 overflow-y-auto">
              {others.map((m) => {
                const on = picked.includes(m.user_id);
                return (
                  <li key={`${m.user_id}-${m.organization_id}`}>
                    <button
                      type="button"
                      onClick={() => toggle(m.user_id)}
                      aria-pressed={on}
                      className={`flex w-full items-center justify-between gap-2 rounded-control border px-3 py-2 text-left transition-colors ${on ? "border-accent bg-accent-soft" : "border-line hover:bg-sunken"}`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-[14px] font-semibold text-ink">{m.name}</span>
                        <span className="block truncate text-[12.5px] text-ink-3">{m.email}</span>
                      </span>
                      <span className={`grid h-5 w-5 shrink-0 place-items-center rounded border ${on ? "border-accent bg-accent text-accent-ink" : "border-line"}`}>
                        {on && <Check className="h-3.5 w-3.5" strokeWidth={2.5} />}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {mode === "email" && (
          <div>
            <label className="field-label" htmlFor={`${id}-to`}>
              Other email addresses
            </label>
            <input id={`${id}-to`} className="field" value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@bank.com, another@bank.com" />
            {badTyped.length > 0 && <p className="mt-1 text-[12.5px] text-danger">Check: {badTyped.join(", ")}</p>}
          </div>
        )}

        {mode === "assign" && (
          <div>
            <label className="field-label" htmlFor={`${id}-due`}>
              Done by (optional)
            </label>
            <input id={`${id}-due`} type="date" className="field" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        )}

        <div>
          <label className="field-label" htmlFor={`${id}-note`}>
            Note (optional)
          </label>
          <textarea id={`${id}-note`} className="field min-h-[72px]" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder={mode === "assign" ? "What should they check or do?" : "Add a line for the reader"} />
        </div>

        <p className="text-[12.5px] text-ink-3">The email holds the checked summary, what banks must do, key dates and the mind map. The original PDF is attached.</p>

        {result && <Notice kind={result.kind}>{result.text}</Notice>}

        <div className="flex flex-wrap justify-end gap-2">
          {mode === "email" && (needFile || recipients.length > 0) && (
            <button type="button" onClick={download} disabled={busy || badTyped.length > 0} className="btn-secondary min-h-[44px] sm:min-h-0">
              <Download className="h-4 w-4" /> Open in my mail app
            </button>
          )}
          <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={onClose}>
            Close
          </button>
          <button type="submit" disabled={!canSend || busy} className="btn-primary min-h-[44px] sm:min-h-0">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : mode === "email" ? `Send${recipients.length ? ` to ${recipients.length}` : ""}` : `Assign${picked.length ? ` to ${picked.length}` : ""}`}
          </button>
        </div>
      </form>
    </Modal>
  );
}
