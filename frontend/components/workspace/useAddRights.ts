"use client";

import { useEffect, useState } from "react";
import type { MyOrg } from "@/services/workspaceApi";
import { loadOrgs, useWorkspace } from "@/services/workspaceStore";

const LAST_ORG_KEY = "regwatch_last_org";
const ADD_ROLES = ["ORG_ADMIN", "COMPLIANCE_HEAD", "COMPLIANCE_OFFICER"];

export function readLastOrg(): string | null {
  try {
    return localStorage.getItem(LAST_ORG_KEY);
  } catch {
    return null;
  }
}

export function rememberOrg(id: string) {
  try {
    localStorage.setItem(LAST_ORG_KEY, id);
  } catch {
    /* private window: the picker simply does not remember */
  }
}

/** The workspaces where the signed-in user may add items to a register, and the one in use. */
export function useAddRights(signedIn: boolean) {
  const ws = useWorkspace();
  const [chosen, setChosen] = useState<string | null>(null);
  useEffect(() => {
    if (signedIn) void loadOrgs();
  }, [signedIn]);
  const eligible: MyOrg[] = signedIn && ws.orgs ? ws.orgs.filter((o) => ADD_ROLES.includes(o.role)) : [];
  const last = typeof window !== "undefined" ? readLastOrg() : null;
  const active = eligible.find((o) => o.id === chosen) ?? eligible.find((o) => o.id === last) ?? eligible[0] ?? null;
  return { eligible, active, setActive: (id: string) => setChosen(id) };
}
