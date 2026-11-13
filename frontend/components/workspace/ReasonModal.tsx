"use client";

import { useEffect, useId, useState } from "react";
import { Modal, ModalHeader } from "../ui";

/** One dialog for every "give a reason first" step: exempt, reopen, cancel a task, withdraw a file, send back. */
export default function ReasonModal({
  open,
  title,
  subtitle,
  label = "Reason",
  confirmLabel,
  required = true,
  initial = "",
  danger = false,
  onClose,
  onConfirm,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  label?: string;
  confirmLabel: string;
  required?: boolean;
  initial?: string;
  danger?: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const id = useId();
  const [text, setText] = useState(initial);
  useEffect(() => {
    if (open) setText(initial);
  }, [open, initial]);
  const ok = !required || text.trim().length > 0;
  return (
    <Modal open={open} onClose={onClose} labelledBy={`${id}-title`} width="max-w-md">
      <ModalHeader id={`${id}-title`} title={title} subtitle={subtitle} onClose={onClose} />
      <form
        className="space-y-4 px-5 py-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!ok) return;
          onConfirm(text.trim());
          onClose();
        }}
      >
        <div>
          <label className="field-label" htmlFor={`${id}-reason`}>
            {label}
          </label>
          <textarea id={`${id}-reason`} className="field min-h-[96px]" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost min-h-[44px] sm:min-h-0" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={!ok} className={`${danger ? "btn-danger" : "btn-primary"} min-h-[44px] sm:min-h-0`}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </Modal>
  );
}
