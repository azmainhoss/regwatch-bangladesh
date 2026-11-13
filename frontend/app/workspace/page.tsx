"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Building2 } from "lucide-react";
import { EmptyState, SkeletonLine } from "@/components/ui";
import { RoleTag } from "@/components/workspace/badges";
import { LoadError, SignInGate, Toast, useSessionUser } from "@/components/workspace/Shell";
import { readLastOrg } from "@/components/workspace/useAddRights";
import { createOrganization } from "@/services/workspaceApi";
import { loadOrgs, setNotice, useWorkspace } from "@/services/workspaceStore";

const ENTITY_TYPES: [string, string][] = [
  ["COMMERCIAL_BANK", "Commercial bank"],
  ["ISLAMIC_BANK", "Islamic bank"],
  ["NBFI", "Non-bank financial institution"],
  ["OTHER", "Other"],
];

export default function WorkspacePicker() {
  const router = useRouter();
  const ws = useWorkspace();
  const { user, ready, setUser } = useSessionUser();
  const [name, setName] = useState("");
  const [type, setType] = useState("COMMERCIAL_BANK");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (user) void loadOrgs();
  }, [user]);

  // One workspace: go straight in.
  useEffect(() => {
    if (ws.orgs && ws.orgs.length === 1) router.replace(`/workspace/${ws.orgs[0].id}`);
  }, [ws.orgs, router]);

  if (!ready) return <SkeletonLine className="h-24 w-full" />;
  if (!user) return <SignInGate user={user} setUser={setUser} />;
  if (ws.orgsError) return <LoadError message={ws.orgsError} onRetry={() => void loadOrgs(true)} />;
  if (!ws.orgs || ws.orgs.length === 1) return <SkeletonLine className="h-24 w-full" />;

  const last = readLastOrg();
  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || creating) return;
    setCreating(true);
    try {
      const org = await createOrganization(name.trim(), type);
      await loadOrgs(true);
      router.push(`/workspace/${org.id}/settings`);
    } catch (err: any) {
      setNotice({ kind: "error", text: `Could not create the workspace: ${err?.message || "unknown error"}` });
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-[22px] font-bold tracking-tight text-ink">Bank workspace</h1>
      {ws.orgs.length > 0 ? (
        <ul className="grid gap-3 sm:grid-cols-2">
          {[...ws.orgs]
            .sort((a, b) => (a.id === last ? -1 : b.id === last ? 1 : a.name.localeCompare(b.name)))
            .map((o) => (
              <li key={o.id}>
                <Link href={`/workspace/${o.id}`} className="panel flex min-h-[72px] items-center gap-3 px-4 py-3 transition-colors hover:border-line-strong hover:bg-sunken/60">
                  <Building2 className="h-5 w-5 shrink-0 text-ink-3" strokeWidth={1.75} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-semibold text-ink">{o.name}</span>
                    <span className="mt-1 block">
                      <RoleTag role={o.role} />
                    </span>
                  </span>
                </Link>
              </li>
            ))}
        </ul>
      ) : (
        <EmptyState title="You are not in a bank workspace yet." icon={<Building2 className="h-6 w-6" />}>
          If your bank already uses RegWatch, ask your admin to add your email. Or create a workspace for your bank below.
        </EmptyState>
      )}
      <form onSubmit={create} className="panel space-y-3 px-4 py-4">
        <h2 className="section-title">Create a workspace</h2>
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end">
          <div>
            <label className="field-label" htmlFor="ws-name">
              Bank name
            </label>
            <input id="ws-name" className="field h-11 sm:h-9" value={name} onChange={(e) => setName(e.target.value)} maxLength={255} required />
          </div>
          <div>
            <label className="field-label" htmlFor="ws-type">
              Type
            </label>
            <select id="ws-type" className="field h-11 py-1 sm:h-9" value={type} onChange={(e) => setType(e.target.value)}>
              {ENTITY_TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <button type="submit" className="btn-primary min-h-[44px] sm:min-h-0" disabled={creating || !name.trim()}>
            Create workspace
          </button>
        </div>
      </form>
      <Toast />
    </div>
  );
}
