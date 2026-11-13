"use client";

import { useMemo } from "react";
import type { DepartmentRead, ItemRead, MemberRead } from "@/services/workspaceApi";
import type { Me } from "@/services/workspaceRules";
import { canEditItem } from "@/services/workspaceRules";

/** Department picker. Saves on change; the list is already in the store, so it opens at once. */
export function DepartmentSelect({
  item,
  me,
  departments,
  onChange,
  className = "",
  id,
}: {
  item: ItemRead;
  me: Me;
  departments: DepartmentRead[];
  onChange: (id: string | null) => void;
  className?: string;
  id?: string;
}) {
  const canEdit = canEditItem(me, item);
  const leadOnly = me.role === "DEPARTMENT_LEAD";
  return (
    <select
      id={id}
      aria-label="Department"
      className={`field h-11 py-1 sm:h-9 ${className}`}
      value={item.department_id ?? ""}
      disabled={!canEdit || leadOnly}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">No department</option>
      {departments.map((d) => (
        <option key={d.id} value={d.id}>
          {d.name}
        </option>
      ))}
    </select>
  );
}

/** Lead picker: people of the item&apos;s department first, then everyone else. */
export function LeadSelect({
  item,
  me,
  members,
  onChange,
  className = "",
  id,
}: {
  item: ItemRead;
  me: Me;
  members: MemberRead[];
  onChange: (userId: string | null) => void;
  className?: string;
  id?: string;
}) {
  const canEdit = canEditItem(me, item);
  const options = useMemo(() => {
    let active = members.filter((m) => m.status === "ACTIVE");
    if (me.role === "DEPARTMENT_LEAD") active = active.filter((m) => m.department_id === me.departmentId);
    const same = active.filter((m) => item.department_id && m.department_id === item.department_id);
    const rest = active.filter((m) => !same.includes(m));
    return { same, rest };
  }, [members, item.department_id, me.role, me.departmentId]);
  const current = item.assigned_lead?.id ?? "";
  const known = [...options.same, ...options.rest].some((m) => m.user.id === current);
  return (
    <select
      id={id}
      aria-label="Lead"
      className={`field h-11 py-1 sm:h-9 ${className}`}
      value={current}
      disabled={!canEdit}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onChange(e.target.value || null)}
    >
      <option value="">No lead</option>
      {current && !known && item.assigned_lead && <option value={current}>{item.assigned_lead.full_name}</option>}
      {options.same.length > 0 && (
        <optgroup label="In this department">
          {options.same.map((m) => (
            <option key={m.id} value={m.user.id}>
              {m.user.full_name}
            </option>
          ))}
        </optgroup>
      )}
      {options.rest.length > 0 && (
        <optgroup label={options.same.length ? "Everyone else" : "People"}>
          {options.rest.map((m) => (
            <option key={m.id} value={m.user.id}>
              {m.user.full_name}
            </option>
          ))}
        </optgroup>
      )}
    </select>
  );
}
