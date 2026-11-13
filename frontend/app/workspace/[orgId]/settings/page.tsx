"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { Plus, Trash2 } from "lucide-react";
import { EmptyState } from "@/components/ui";
import { Tag } from "@/components/StatusBadge";
import { ListSkeleton } from "@/components/workspace/Shell";
import { ROLES, ROLE_LABEL, type DepartmentRead, type MemberRead } from "@/services/workspaceApi";
import { addDepartmentNow, addMemberNow, changeDepartment, changeMember, removeDepartment, useWorkspace, departmentsOf, membersOf } from "@/services/workspaceStore";

function DepartmentRow({ orgId, dept, members, canDelete }: { orgId: string; dept: DepartmentRead; members: MemberRead[]; canDelete: boolean }) {
  const [name, setName] = useState(dept.name);
  const [editing, setEditing] = useState(false);
  const pendingNew = dept.id.startsWith("tmp:");
  const commit = () => {
    setEditing(false);
    const next = name.trim();
    if (next && next !== dept.name) void changeDepartment(orgId, dept.id, { name: next });
    else setName(dept.name);
  };
  return (
    <li className={`grid gap-2 px-4 py-3 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1.2fr)_auto_auto_auto] md:items-center md:gap-4 ${pendingNew ? "opacity-60" : ""}`} data-testid="department-row">
      <div>
        <label className="sr-only" htmlFor={`dn-${dept.id}`}>
          Department name
        </label>
        <input
          id={`dn-${dept.id}`}
          className="field h-11 sm:h-9"
          value={editing ? name : dept.name}
          onFocus={() => {
            setName(dept.name);
            setEditing(true);
          }}
          onChange={(e) => setName(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          disabled={pendingNew}
          maxLength={128}
        />
      </div>
      <div>
        <label className="sr-only" htmlFor={`dh-${dept.id}`}>
          Department head
        </label>
        <select id={`dh-${dept.id}`} className="field h-11 py-1 sm:h-9" value={dept.head_user_id ?? ""} disabled={pendingNew} onChange={(e) => void changeDepartment(orgId, dept.id, { head_user_id: e.target.value || null })}>
          <option value="">No head</option>
          {members
            .filter((m) => m.status === "ACTIVE")
            .map((m) => (
              <option key={m.id} value={m.user.id}>
                {m.user.full_name}
              </option>
            ))}
        </select>
      </div>
      <span className="text-[13px] text-ink-3 tabular-nums">{dept.member_count} member{dept.member_count === 1 ? "" : "s"}</span>
      <span className="text-[13px] text-ink-3 tabular-nums">{dept.open_item_count} open item{dept.open_item_count === 1 ? "" : "s"}</span>
      {canDelete ? (
        <button
          type="button"
          className="btn-ghost min-h-[44px] text-bad sm:min-h-0"
          disabled={dept.open_item_count > 0 || pendingNew}
          title={dept.open_item_count > 0 ? "Move its items first" : "Delete this department"}
          onClick={() => void removeDepartment(orgId, dept.id)}
        >
          <Trash2 className="h-4 w-4" /> {dept.open_item_count > 0 ? "Move its items first" : "Delete"}
        </button>
      ) : (
        <span />
      )}
    </li>
  );
}

function MemberRowView({ orgId, m, departments, canEdit, me }: { orgId: string; m: MemberRead; departments: DepartmentRead[]; canEdit: boolean; me: string }) {
  const locked = !canEdit;
  return (
    <li className="grid gap-2 px-4 py-3 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1.2fr)_auto] md:items-center md:gap-4" data-testid="member-row">
      <div className="min-w-0">
        <span className="block truncate text-[14.5px] font-semibold text-ink">
          {m.user.full_name} {m.user.id === me && <Tag tone="muted">You</Tag>}
        </span>
        <span className="block truncate text-[12.5px] text-ink-3">{m.user.email}</span>
      </div>
      <div>
        <label className="sr-only" htmlFor={`mr-${m.id}`}>
          Role of {m.user.full_name}
        </label>
        <select id={`mr-${m.id}`} className="field h-11 py-1 sm:h-9" value={m.role} disabled={locked} onChange={(e) => void changeMember(orgId, m.id, { role: e.target.value })}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="sr-only" htmlFor={`md-${m.id}`}>
          Department of {m.user.full_name}
        </label>
        <select id={`md-${m.id}`} className="field h-11 py-1 sm:h-9" value={m.department_id ?? ""} disabled={locked} onChange={(e) => void changeMember(orgId, m.id, { department_id: e.target.value || null })}>
          <option value="">No department</option>
          {departments.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        {m.status !== "ACTIVE" && <Tag tone="warn">{m.status === "SUSPENDED" ? "Suspended" : "Invited"}</Tag>}
        {!locked && (
          <button type="button" className="btn-secondary min-h-[44px] sm:min-h-0" onClick={() => void changeMember(orgId, m.id, { status: m.status === "SUSPENDED" ? "ACTIVE" : "SUSPENDED" })}>
            {m.status === "SUSPENDED" ? "Reactivate" : "Suspend"}
          </button>
        )}
      </div>
    </li>
  );
}

export default function SettingsPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const ws = useWorkspace();
  const perms = ws.me[orgId]?.permissions;
  const me = ws.me[orgId];
  const departments = departmentsOf(ws, orgId);
  const members = membersOf(ws, orgId);
  const [deptName, setDeptName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("ANALYST");
  const [memberDept, setMemberDept] = useState("");
  const [adding, setAdding] = useState(false);
  const loaded = ws.loaded[`members:${orgId}`] === "ok" && ws.loaded[`departments:${orgId}`] === "ok";

  if (!perms || !me) return null;
  if (!perms.manage_members && !perms.manage_departments) return <EmptyState title="You do not have access to the settings." />;
  const isAdmin = me.membership.role === "ORG_ADMIN";
  const canEditMember = (m: MemberRead) => perms.manage_members && (isAdmin || m.role !== "ORG_ADMIN");
  if (!loaded) return <ListSkeleton rows={3} />;

  return (
    <div className="space-y-8" data-testid="settings-page">
      {perms.manage_departments && (
        <section aria-label="Departments" className="space-y-3">
          <h2 className="text-[18px] font-bold text-ink">Departments</h2>
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const name = deptName.trim();
              if (!name) return;
              setDeptName("");
              const ok = await addDepartmentNow(orgId, name, null);
              if (!ok) setDeptName(name);
            }}
          >
            <div className="min-w-[12rem] flex-1">
              <label className="field-label" htmlFor="new-dept">
                New department
              </label>
              <input id="new-dept" className="field h-11 sm:h-9" value={deptName} onChange={(e) => setDeptName(e.target.value)} maxLength={128} placeholder="For example Credit, Treasury, AML" />
            </div>
            <button type="submit" className="btn-primary min-h-[44px] sm:min-h-0" disabled={!deptName.trim()}>
              <Plus className="h-4 w-4" /> Add
            </button>
          </form>
          {departments.length === 0 ? (
            <EmptyState title="No departments yet.">Add the departments of your bank, then add the people who work in them.</EmptyState>
          ) : (
            <ul className="panel divide-y divide-line overflow-hidden">
              {departments.map((d) => (
                <DepartmentRow key={d.id} orgId={orgId} dept={d} members={members} canDelete={isAdmin} />
              ))}
            </ul>
          )}
        </section>
      )}

      {perms.manage_members && (
        <section aria-label="Members" className="space-y-3">
          <h2 className="text-[18px] font-bold text-ink">Members</h2>
          <form
            className="panel grid gap-3 px-4 py-4 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end"
            onSubmit={async (e) => {
              e.preventDefault();
              if (!email.trim() || adding) return;
              setAdding(true);
              const added = await addMemberNow(orgId, email.trim(), role, memberDept || null);
              setAdding(false);
              if (added) setEmail("");
            }}
          >
            <div>
              <label className="field-label" htmlFor="new-email">
                Add a member by email
              </label>
              <input id="new-email" type="email" className="field h-11 sm:h-9" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@bank.com" required />
            </div>
            <div>
              <label className="field-label" htmlFor="new-role">
                Role
              </label>
              <select id="new-role" className="field h-11 py-1 sm:h-9" value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.filter((r) => isAdmin || r !== "ORG_ADMIN").map((r) => (
                  <option key={r} value={r}>
                    {ROLE_LABEL[r]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="new-dept-member">
                Department
              </label>
              <select id="new-dept-member" className="field h-11 py-1 sm:h-9" value={memberDept} onChange={(e) => setMemberDept(e.target.value)}>
                <option value="">No department</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
            <button type="submit" className="btn-primary min-h-[44px] sm:min-h-0" disabled={adding || !email.trim()}>
              Add member
            </button>
          </form>
          <ul className="panel divide-y divide-line overflow-hidden">
            {members.map((m) => (
              <MemberRowView key={m.id} orgId={orgId} m={m} departments={departments} canEdit={canEditMember(m)} me={me.membership.user.id} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
