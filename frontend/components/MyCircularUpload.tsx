"use client";

import { useState } from "react";
import { Lock, UploadCloud } from "lucide-react";
import { Institution, uploadDocument } from "@/services/api";

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
      setTitle("");
      setRefNumber("");
      onUploaded();
    } catch (err: any) {
      setMessage({ type: "error", text: err.message || "Upload failed." });
    } finally {
      setBusy(false);
    }
  };

  const inputClass =
    "w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-lg px-3 py-1.5 text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise";

  return (
    <div className="border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/80 dark:bg-tealNavy-900/80 light:bg-white rounded-xl p-4 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between font-mono font-semibold text-slate-200 dark:text-slate-200 light:text-tealNavy-950"
      >
        <span className="flex items-center gap-2">
          <Lock className="w-3.5 h-3.5 text-turquoise" />
          My circulars, only you can see these
        </span>
        <span className="text-turquoise">{open ? "Close" : "Upload a PDF"}</span>
      </button>

      {open && (
        <form onSubmit={handleSubmit} className="space-y-2.5 mt-3">
          <p className="text-slate-400">
            Files you add here are private. Nobody else, including administrators, can see them.
          </p>
          <input
            type="file"
            accept=".pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="w-full text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-bold file:bg-turquoise file:text-tealNavy-950 cursor-pointer"
          />
          <select value={chosenInstitution} onChange={(e) => setInstitutionId(e.target.value)} className={inputClass}>
            {institutions.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.name} ({inst.code})
              </option>
            ))}
          </select>
          <input type="text" placeholder="Title *" value={title} onChange={(e) => setTitle(e.target.value)} className={inputClass} />
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text"
              placeholder="Reference number"
              value={refNumber}
              onChange={(e) => setRefNumber(e.target.value)}
              className={`${inputClass} font-mono`}
            />
            <input type="date" value={pubDate} onChange={(e) => setPubDate(e.target.value)} className={`${inputClass} font-mono`} />
          </div>
          {message && (
            <p className={message.type === "success" ? "text-emerald-400" : "text-rose-300"}>{message.text}</p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="w-full py-2 bg-turquoise hover:bg-turquoise-bright disabled:opacity-50 text-tealNavy-950 font-bold rounded-lg flex items-center justify-center gap-2 font-mono"
          >
            <UploadCloud className="w-3.5 h-3.5" />
            <span>{busy ? "Uploading..." : "Upload privately"}</span>
          </button>
        </form>
      )}
    </div>
  );
}
