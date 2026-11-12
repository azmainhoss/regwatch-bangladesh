"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";

export const EASE_OUT = [0.16, 1, 0.3, 1] as const;

type NoticeKind = "success" | "warning" | "error" | "info";

const NOTICE_STYLE: Record<NoticeKind, { cls: string; Icon: typeof Info }> = {
  success: { cls: "bg-ok-soft text-ok ring-ok/25", Icon: CheckCircle2 },
  warning: { cls: "bg-warn-soft text-warn ring-warn/30", Icon: AlertTriangle },
  error: { cls: "bg-bad-soft text-bad ring-bad/25", Icon: AlertTriangle },
  info: { cls: "bg-info-soft text-info ring-info/25", Icon: Info },
};

/** Inline message for results and errors. Errors are announced to screen readers. */
export function Notice({
  kind,
  children,
  onDismiss,
  className = "",
}: {
  kind: NoticeKind;
  children: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
}) {
  const { cls, Icon } = NOTICE_STYLE[kind];
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE_OUT }}
      role={kind === "error" ? "alert" : "status"}
      className={`flex items-start gap-2.5 rounded-panel px-3.5 py-2.5 text-[13.5px] leading-snug ring-1 ring-inset ${cls} ${className}`}
    >
      <Icon className="mt-px h-4 w-4 shrink-0" strokeWidth={2} aria-hidden />
      <div className="min-w-0 flex-1 break-words text-ink">{children}</div>
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label="Dismiss" className="-m-1 rounded p-1 text-ink-3 hover:text-ink">
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </motion.div>
  );
}

/** Dialog with a backdrop. Escape and backdrop click close it; focus moves into it on open. */
export function Modal({
  open,
  onClose,
  labelledBy,
  children,
  width = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  children: React.ReactNode;
  width?: string;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const t = window.setTimeout(() => {
      const first =
        panelRef.current?.querySelector<HTMLElement>("input, select, textarea") ??
        panelRef.current?.querySelector<HTMLElement>("button, a");
      first?.focus();
    }, 30);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      window.clearTimeout(t);
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[60] flex items-end justify-center p-0 sm:items-center sm:p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <div className="absolute inset-0 bg-[rgb(var(--shadow)/0.45)]" onClick={onClose} aria-hidden />
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={labelledBy}
            initial={{ opacity: 0, y: 16, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.99 }}
            transition={{ duration: 0.24, ease: EASE_OUT }}
            className={`relative w-full ${width} max-h-[92dvh] overflow-hidden rounded-t-panel border border-line bg-surface shadow-pop sm:rounded-panel`}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function ModalHeader({ id, title, subtitle, onClose }: { id: string; title: string; subtitle?: string; onClose: () => void }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div>
        <h2 id={id} className="text-[17px] font-semibold text-ink">
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-[13px] text-ink-3">{subtitle}</p>}
      </div>
      <button type="button" onClick={onClose} aria-label="Close" className="btn-ghost -mr-2 h-8 w-8 p-0">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function SkeletonLine({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-sunken ${className}`} />;
}

export function EmptyState({ title, children, icon }: { title: string; children?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-panel border border-dashed border-line-strong px-6 py-10 text-center">
      {icon && <div className="mb-3 text-ink-3">{icon}</div>}
      <p className="text-[15px] font-semibold text-ink">{title}</p>
      {children && <div className="mt-1 max-w-sm text-[13.5px] leading-relaxed text-ink-3">{children}</div>}
    </div>
  );
}

/** Drops a leading "<reference number>:" from a title, since the reference is shown on its own line. */
export function titleWithoutRef(title: string, ref?: string | null) {
  if (!ref) return title;
  const t = title.trim();
  if (t.toLowerCase().startsWith(ref.trim().toLowerCase())) {
    const rest = t.slice(ref.trim().length).replace(/^[\s:.\-]+/, "");
    if (rest.length > 3) return rest.charAt(0).toUpperCase() + rest.slice(1);
  }
  return title;
}

/** True when the text holds Bangla script, so it can be tagged lang="bn". */
export function hasBangla(text?: string | null) {
  return !!text && /[ঀ-৿]/.test(text);
}
