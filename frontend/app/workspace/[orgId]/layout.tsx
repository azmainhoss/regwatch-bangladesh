"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Notice, SkeletonLine } from "@/components/ui";
import { RoleTag } from "@/components/workspace/badges";
import { LoadError, SignInGate, Toast, useSessionUser } from "@/components/workspace/Shell";
import WorkspaceNav from "@/components/workspace/WorkspaceNav";
import { rememberOrg } from "@/components/workspace/useAddRights";
import { ensureWorkspace, loadMe, loadOrgs, startSync, useWorkspace } from "@/services/workspaceStore";

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ orgId: string }>();
  const orgId = params.orgId;
  const ws = useWorkspace();
  const { user, ready, setUser } = useSessionUser();

  useEffect(() => {
    if (!user) return;
    rememberOrg(orgId);
    void loadOrgs();
    void ensureWorkspace(orgId);
    return startSync(orgId);
  }, [orgId, user]);

  if (!ready) return <SkeletonLine className="h-24 w-full" />;
  if (!user) return <SignInGate user={user} setUser={setUser} />;

  const meState = ws.loaded[`me:${orgId}`];
  const me = ws.me[orgId];
  const org = ws.orgs?.find((o) => o.id === orgId);

  if (typeof meState === "object") {
    const forbidden = /not an active member|Cross-tenant|forbidden/i.test(meState.error);
    return (
      <div className="mx-auto max-w-lg space-y-4">
        {forbidden ? (
          <Notice kind="error">
            You are not a member of this workspace.{" "}
            <Link href="/workspace" className="font-semibold text-accent underline">
              Back to your workspaces
            </Link>
          </Notice>
        ) : (
          <LoadError message={meState.error} onRetry={() => void loadMe(orgId, true)} />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="no-print flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-[20px] font-bold tracking-tight text-ink sm:text-[22px]">{org?.name ?? (me ? "Workspace" : "")}</h1>
        {me && <RoleTag role={me.membership.role} />}
        <Link href="/workspace" className="ml-auto text-[13px] font-semibold text-ink-3 hover:text-ink">
          All workspaces
        </Link>
      </div>
      <div className="no-print">
        <WorkspaceNav orgId={orgId} />
      </div>
      {!me ? <SkeletonLine className="h-40 w-full" /> : children}
      <Toast />
    </div>
  );
}
