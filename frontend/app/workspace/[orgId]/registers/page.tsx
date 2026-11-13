"use client";

import { Suspense, useEffect, useId, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Archive, ArchiveRestore, MoreHorizontal, Pencil, Plus } from "lucide-react";
import { EmptyState, Modal, ModalHeader } from "@/components/ui";
import { Tag } from "@/components/StatusBadge";
import { ListSkeleton } from "@/components/workspace/Shell";
import type { RegisterRead } from "@/services/workspaceApi";
import { countItems } from "@/services/workspaceRules";
import { addRegister, changeRegister, orgItems, orgRegisters, registerItems, useWorkspace } from "@/services/workspaceStore";

function CountsBar({ c }: { c: ReturnType<typeof countItems> }) {
  const parts: [string, number, string][] = [
    ["Compliant", c.compliant, "bg-ok"],
    ["Waiting sign-off", c.evidence_submitted, "bg-warn"],
    ["In progress", c.in_progress, "bg-info"],
    ["Overdue", c.overdue, "bg-bad"],
    ["Not started", c.not_started, "bg-line-strong"],
    ["Exempted", c.exempted, "bg-muted"],
  ];
  if (c.total === 0) return <div className="h-2 rounded-full bg-sunken" aria-hidden />;
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-sunken" role="img" aria-label={parts.map(([l, n]) => `${n} ${l.toLowerCase()}`).join(", ")}>
        {parts.map(([l, n, cls]) => (n > 0 ? <span key={l} className={cls} style={{ width: `${(n / c.total) * 100}%` }} title={`${l}: ${n}`} /> : null))}
      </div>
      <p className="mt-1.5 text-[12.5px] text-ink-3 tabular-nums">
        {c.compliant} compliant, {c.in_progress} in progress, {c.overdue} overdue, {c.not_started} not started
      </p>
    </div>
  );
}

function RegisterCard({ orgId, register, canManage, onRename }: { orgId: string; register: RegisterRead; canManage: boolean; onRename: (r: RegisterRead) => void }) {
  const ws = useWorkspace();
  const items = registerItems(ws, orgId, register.id);
  const counts = countItems(items, ws.today);
  const sources = new Set(items.map((i) => i.source.document_id).filter(Boolean)).size;
  const [menu, setMenu] = useState(false);
  const pendingNew = register.id.startsWith("tmp:");
  return (
    <li className={`panel relative ${pendingNew ? "opacity-60" : ""}`} data-testid="register-card" data-register-id={register.id}>
      <Link href={pendingNew ? "#" : `/workspace/${orgId}/registers/${register.id}`} className="block min-h-[96px] px-4 py-3.5 pr-12">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-[16px] font-semibold text-ink">{register.title}</span>
          {!register.is_active && <Tag tone="muted">Archived</Tag>}
        </span>
        {register.description && <span className="mt-0.5 block text-[13.5px] text-ink-3">{register.description}</span>}
        <span className="mt-3 block">
          <CountsBar c={counts} />
        </span>
        <span className="mt-2 block text-[12.5px] text-ink-3">
          {counts.total} item{counts.total === 1 ? "" : "s"}, {sources} source circular{sources === 1 ? "" : "s"}
          {counts.flagged > 0 && <span className="ml-2 font-semibold text-warn">{counts.flagged} circular changed</span>}
        </span>
      </Link>
      {canManage && !pendingNew && (
        <div className="absolute right-2 top-2">
          <button type="button" aria-label="Register menu" aria-expanded={menu} className="btn-ghost h-11 w-11 p-0 sm:h-9 sm:w-9" onClick={() => setMenu((m) => !m)}>
            <MoreHorizontal className="h-4 w-4" />
          </button>
          {menu && (
            <div className="absolute right-0 z-10 mt-1 w-44 rounded-control border border-line bg-surface py-1 shadow-pop" role="menu" onMouseLeave={() => setMenu(false)}>
              <button type="button" role="menuitem" className="flex min-h-[44px] w-full items-center gap-2 px-3 text-left text-[14px] hover:bg-sunken" onClick={() => { setMenu(false); onRename(register); }}>
                <Pencil className="h-4 w-4" /> Rename
              </button>
              <button type="button" role="menuitem" className="flex min-h-[44px] w-full items-center gap-2 px-3 text-left text-[14px] hover:bg-sunken" onClick={() => { setMenu(false); void changeRegister(orgId, register.id, { is_active: !register.is_active }); }}>
                {register.is_active ? <Archive className="h-4 w-4" /> : <ArchiveRestore className="h-4 w-4" />}
                {register.is_active ? "Archive" : "Unarchive"}
              </button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function RegisterForm({ open, onClose, orgId, register }: { open: boolean; onClose: () => void; orgId: string; register: RegisterRead | null }) {
  const id = useId();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  useEffect(() => {
    if (open) {
      setTitle(register?.title ?? "");
      setDescription(register?.description ?? "");
    }
  }, [open, register]);
  return (
    <Modal open={open} onClose={onClose} labelledBy={`${id}-t`} width="max-w-md">
      <ModalHeader id={`${id}-t`} title={register ? "Rename register" : "New register"} onClose={onClose} />
      <form
        className="space-y-4 px-5 py-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!title.trim()) return;
          if (register) void changeRegister(orgId, register.id, { title: title.trim(), description: description.trim() || null });
          else void addRegister(orgId, title.trim(), description.trim());
          onClose();
        }}
      >
        <div>
          <label className="field-label" htmlFor={`${id}-n`}>
            Title
          </label>
          <input id={`${id}-n`} className="field h-11 sm:h-9" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} required />
        </div>
        <div>
          <label className="field-label" htmlFor={`${id}-d`}>
            Description (optional)
          </label>
          <textarea id={`${id}-d`} className="field min-h-[72px]" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary min-h-[44px] sm:min-h-0" disabled={!title.trim()}>
            {register ? "Save" : "Create register"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function RegistersInner() {
  const { orgId } = useParams<{ orgId: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const ws = useWorkspace();
  const perms = ws.me[orgId]?.permissions;
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<RegisterRead | null>(null);
  const loaded = ws.loaded[`registers:${orgId}`] === "ok" && ws.loaded[`items:${orgId}`] === "ok";
  const registers = orgRegisters(ws, orgId, showArchived);
  const all = orgRegisters(ws, orgId, true);
  const archivedCount = all.filter((r) => !r.is_active).length;
  const itemCount = orgItems(ws, orgId).length;

  useEffect(() => {
    if (search.get("new") === "1" && perms?.manage_registers) {
      setCreating(true);
      router.replace(`/workspace/${orgId}/registers`, { scroll: false });
    }
  }, [search, perms?.manage_registers, orgId, router]);

  return (
    <div className="space-y-4" data-testid="registers-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[18px] font-bold text-ink">Registers</h2>
        <div className="flex flex-wrap items-center gap-3">
          {archivedCount > 0 && (
            <label className="flex min-h-[44px] items-center gap-2 text-[13.5px] font-semibold text-ink-2 sm:min-h-0">
              <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--accent))]" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
              Show archived
            </label>
          )}
          {itemCount > 0 && (
            <Link href={`/workspace/${orgId}/registers/all`} className="btn-secondary min-h-[44px] sm:min-h-0">
              All items
            </Link>
          )}
          {perms?.manage_registers && (
            <button type="button" className="btn-primary min-h-[44px] sm:min-h-0" onClick={() => setCreating(true)} data-testid="new-register">
              <Plus className="h-4 w-4" /> New register
            </button>
          )}
        </div>
      </div>
      {!loaded ? (
        <ListSkeleton rows={3} />
      ) : registers.length === 0 ? (
        <EmptyState title="No registers yet.">
          <span className="mt-2 flex flex-wrap justify-center gap-2">
            {perms?.manage_registers && (
              <button type="button" className="btn-primary min-h-[44px] sm:min-h-0" onClick={() => setCreating(true)}>
                New register
              </button>
            )}
            <Link href="/" className="btn-secondary min-h-[44px] sm:min-h-0">
              Browse circulars
            </Link>
          </span>
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {registers.map((r) => (
            <RegisterCard key={r.id} orgId={orgId} register={r} canManage={!!perms?.manage_registers} onRename={setRenaming} />
          ))}
        </ul>
      )}
      <RegisterForm open={creating} onClose={() => setCreating(false)} orgId={orgId} register={null} />
      <RegisterForm open={!!renaming} onClose={() => setRenaming(null)} orgId={orgId} register={renaming} />
    </div>
  );
}

export default function RegistersPage() {
  return (
    <Suspense fallback={<ListSkeleton rows={3} />}>
      <RegistersInner />
    </Suspense>
  );
}
