"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";

/** A date box that saves when you leave it or press Enter, and only if the value changed. */
export default function DeadlineField({
  value,
  onSave,
  disabled,
  label,
  id,
}: {
  value: string | null;
  onSave: (next: string | null) => void;
  disabled?: boolean;
  label: string;
  id?: string;
}) {
  const [text, setText] = useState(value ?? "");
  const focused = useRef(false);
  // The value last sent, so Enter followed by leaving the box never saves the same date twice.
  const sent = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    sent.current = undefined;
    if (!focused.current) setText(value ?? "");
  }, [value]);

  const commit = (next: string) => {
    const clean = next || null;
    if (clean === (value ?? null) || clean === sent.current) return;
    sent.current = clean;
    onSave(clean);
  };

  return (
    <div className="flex items-center gap-1.5">
      <input
        id={id}
        type="date"
        aria-label={label}
        className="field h-11 min-w-0 flex-1 py-1 sm:h-9"
        value={text}
        disabled={disabled}
        onFocus={() => (focused.current = true)}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          focused.current = false;
          commit(text);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit(text);
            (e.target as HTMLInputElement).blur();
          }
        }}
      />
      {!disabled && value && (
        <button
          type="button"
          aria-label={`Clear ${label.toLowerCase()}`}
          className="btn-ghost h-11 w-11 shrink-0 p-0 sm:h-9 sm:w-9"
          onClick={() => {
            setText("");
            sent.current = null;
            onSave(null);
          }}
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
