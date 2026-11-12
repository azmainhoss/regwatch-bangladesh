"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, Lock, UploadCloud } from "lucide-react";
import { Institution, uploadDocument } from "@/services/api";
import { EASE_OUT, Notice } from "./ui";

interface Props {
  institutions: Institution[];
  onUploaded: () => void;
}

/** Upload form for signed-in users. Their uploads are always private to them. */
export default function MyCircularUpload({ institutions, onUploaded }: Props) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [institutionId, setInstitutionId] = useState("");
  const [title, setTitle] = useState("");
  const [refNumber, setRefNumber] = useState("");
  const [pubDate, setPubDate] = useState(new Date().toISOString().split("T")[0]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [fileKey, setFileKey] = useState(0);

  const chosenInstitution = institutionId || institutions[0]?.id || "";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !chosenInstitution || !title || !pubDate) {
      setMessage({ type: "error", text: "Choose a PDF and fill in the regulator, title and date." });
      return;
    }
    try {
      setBusy(true);
      setMessage(null);
      const formData = new FormData();
      formData.append("file", file);
      formData.append("institution_id", chosenInstitution);
      formData.append("title", title);
      formData.append("publication_date", pubDate);
      if (refNumber) formData.append("reference_number", refNumber);
      formData.append("visibility", "private");
      const result = await uploadDocument(formData);
      setMessage({ type: "success", text: `Added "${result.document.title}" to your private circulars.` });
      setFile(null);
      setFileKey((k) => k + 1);
      setTitle("");
      setRefNumber("");
      onUploaded();
    } catch (err: any) {
      setMessage({ type: "error", text: err.message || "Upload failed." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-panel border border-line bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left"
      >
        <span className="flex items-center gap-2 text-[14px] font-semibold text-ink">
          <Lock className="h-4 w-4 text-ink-3" strokeWidth={1.75} />
          Add a private circular
        </span>
        <motion.span animate={{ rotate: open ? 180 : 0 }} transition={{ duration: 0.2 }} className="text-ink-3">
          <ChevronDown className="h-4 w-4" />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: EASE_OUT }}
            className="overflow-hidden"
          >
            <form onSubmit={handleSubmit} className="space-y-3 border-t border-line px-3.5 pb-3.5 pt-3">
              <p className="text-[13px] leading-relaxed text-ink-3">
                Only you can see files you add here. Administrators cannot see them either.
              </p>
              <div>
                <label htmlFor="my-file" className="field-label">
                  PDF file
                </label>
                <input
                  key={fileKey}
                  id="my-file"
                  type="file"
                  accept=".pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                  className="w-full cursor-pointer text-[13px] text-ink-2 file:mr-3 file:cursor-pointer file:rounded-control file:border file:border-line-strong file:bg-sunken file:px-3 file:py-1.5 file:text-[13px] file:font-semibold file:text-ink hover:file:bg-line"
                />
              </div>
              <div>
                <label htmlFor="my-inst" className="field-label">
                  Regulator
                </label>
                <select id="my-inst" value={chosenInstitution} onChange={(e) => setInstitutionId(e.target.value)} className="field">
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name} ({inst.code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="my-title" className="field-label">
                  Title
                </label>
                <input id="my-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} className="field" required />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label htmlFor="my-ref" className="field-label">
                    Reference number
                  </label>
                  <input id="my-ref" type="text" value={refNumber} onChange={(e) => setRefNumber(e.target.value)} className="field font-mono text-[13px]" />
                </div>
                <div>
                  <label htmlFor="my-date" className="field-label">
                    Date issued
                  </label>
                  <input id="my-date" type="date" value={pubDate} onChange={(e) => setPubDate(e.target.value)} className="field tabular-nums" />
                </div>
              </div>
              {message && <Notice kind={message.type === "success" ? "success" : "error"}>{message.text}</Notice>}
              <button type="submit" disabled={busy} className="btn-primary w-full py-2">
                <UploadCloud className="h-4 w-4" strokeWidth={1.75} />
                {busy ? "Uploading..." : "Upload privately"}
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
