"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { DocumentItem, Institution, fetchDocuments, fetchInstitutions, uploadDocument } from "@/services/api";

export default function AdminConsolePage() {
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Upload Form State
  const [file, setFile] = useState<File | null>(null);
  const [institutionId, setInstitutionId] = useState("");
  const [departmentId, setDepartmentId] = useState("");
  const [refNumber, setRefNumber] = useState("");
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState("CIRCULAR");
  const [pubDate, setPubDate] = useState(new Date().toISOString().split("T")[0]);
  const [effectiveDate, setEffectiveDate] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const [insts, docs] = await Promise.all([
        fetchInstitutions(),
        fetchDocuments()
      ]);
      setInstitutions(insts);
      if (insts.length > 0) {
        setInstitutionId(insts[0].id);
        if (insts[0].departments.length > 0) {
          setDepartmentId(insts[0].departments[0].id);
        }
      }
      setDocuments(docs);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      setUploadMessage({ type: "error", text: "Please select an official PDF file." });
      return;
    }
    if (!institutionId || !title || !pubDate) {
      setUploadMessage({ type: "error", text: "Institution, Title, and Publication Date are required." });
      return;
    }

    try {
      setUploading(true);
      setUploadMessage(null);

      const formData = new FormData();
      formData.append("file", file);
      formData.append("institution_id", institutionId);
      if (departmentId) formData.append("department_id", departmentId);
      if (refNumber) formData.append("reference_number", refNumber);
      formData.append("title", title);
      formData.append("document_type", docType);
      formData.append("publication_date", pubDate);
      if (effectiveDate) formData.append("effective_date", effectiveDate);
      if (sourceUrl) formData.append("source_url", sourceUrl);

      const result = await uploadDocument(formData);
      setUploadMessage({
        type: "success",
        text: `Success! Ingested "${result.document.title}" (${result.pages_extracted} pages extracted, SHA-256: ${result.version.file_sha256.substring(0, 16)}...)`
      });

      // Reset form
      setFile(null);
      setRefNumber("");
      setTitle("");
      setSourceUrl("");
      // Reload documents list
      const refreshedDocs = await fetchDocuments();
      setDocuments(refreshedDocs);
    } catch (err: any) {
      setUploadMessage({ type: "error", text: err.message || "Failed to upload document" });
    } finally {
      setUploading(false);
    }
  };

  const selectedInst = institutions.find((i) => i.id === institutionId);

  return (
    <div className="space-y-8">
      {/* Admin Header */}
      <div className="border border-slate-800 bg-slate-900/60 rounded-xl p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs px-2 py-0.5 rounded bg-brand-900/80 text-brand-300 font-mono border border-brand-700/50">
                ADMIN CONSOLE
              </span>
              <span className="text-xs text-slate-500 font-mono">Platform Operator Mode</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white mt-1">
              Source Registry & Document Ingestion Dropzone
            </h1>
            <p className="text-sm text-slate-400 mt-0.5">
              Manage external source connectors, view crawl logs, and manually submit verified official regulatory PDFs.
            </p>
          </div>
          <Link
            href="/"
            className="text-xs font-mono text-slate-400 hover:text-white px-3 py-1.5 rounded border border-slate-800 bg-slate-950 transition self-start sm:self-auto"
          >
            ← Back to Professional Feed
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column: Official PDF Dropzone Form */}
        <div className="lg:col-span-6 border border-slate-800 bg-slate-900/40 rounded-xl p-6 space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-white">Manual Ingestion Dropzone</h2>
            <p className="text-xs text-slate-400 mt-1">
              Upload an official circular PDF. The system will compute the SHA-256 hash, store it in immutable storage, and perform page-by-page text extraction.
            </p>
          </div>

          {uploadMessage && (
            <div
              className={`p-3 rounded-lg text-xs font-mono ${
                uploadMessage.type === "success"
                  ? "bg-emerald-950/80 border border-emerald-800 text-emerald-300"
                  : "bg-rose-950/80 border border-rose-800 text-rose-300"
              }`}
            >
              {uploadMessage.text}
            </div>
          )}

          <form onSubmit={handleUpload} className="space-y-4 text-xs font-sans">
            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Official PDF File *</label>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="w-full text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-brand-600 file:text-white hover:file:bg-brand-500 cursor-pointer border border-slate-800 rounded-lg p-2 bg-slate-950"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Regulatory Institution *</label>
                <select
                  value={institutionId}
                  onChange={(e) => {
                    setInstitutionId(e.target.value);
                    const inst = institutions.find((i) => i.id === e.target.value);
                    if (inst && inst.departments.length > 0) {
                      setDepartmentId(inst.departments[0].id);
                    } else {
                      setDepartmentId("");
                    }
                  }}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  {institutions.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name} ({inst.code})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Department</label>
                <select
                  value={departmentId}
                  onChange={(e) => setDepartmentId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  <option value="">-- Unspecified --</option>
                  {selectedInst?.departments.map((dept) => (
                    <option key={dept.id} value={dept.id}>
                      {dept.code} - {dept.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Reference Number</label>
                <input
                  type="text"
                  placeholder="e.g. BRPD Circular No. 15/2024"
                  value={refNumber}
                  onChange={(e) => setRefNumber(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Document Type</label>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
                >
                  <option value="CIRCULAR">CIRCULAR</option>
                  <option value="CIRCULAR_LETTER">CIRCULAR_LETTER</option>
                  <option value="GUIDELINE">GUIDELINE</option>
                  <option value="NOTIFICATION">NOTIFICATION</option>
                  <option value="POLICY">POLICY</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Document Title *</label>
              <input
                type="text"
                placeholder="Full official circular subject / title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Publication Date *</label>
                <input
                  type="date"
                  value={pubDate}
                  onChange={(e) => setPubDate(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1.5">Effective Date</label>
                <input
                  type="date"
                  value={effectiveDate}
                  onChange={(e) => setEffectiveDate(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1.5">Original Source URL (Optional)</label>
              <input
                type="url"
                placeholder="https://www.bb.org.bd/mediaroom/circulars/..."
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 font-mono"
              />
            </div>

            <button
              type="submit"
              disabled={uploading}
              className="w-full py-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-semibold rounded-lg shadow transition font-sans text-xs tracking-wide uppercase mt-4"
            >
              {uploading ? "Ingesting & Extracting Pages..." : "Ingest Document & Process"}
            </button>
          </form>
        </div>

        {/* Right Column: Source Status & Ingested Document Log */}
        <div className="lg:col-span-6 space-y-6">
          {/* Source Monitor Card */}
          <div className="border border-slate-800 bg-slate-900/40 rounded-xl p-6">
            <h2 className="text-sm font-semibold text-white uppercase tracking-wider font-mono">
              Registered Source Connectors
            </h2>
            <div className="mt-4 space-y-3">
              <div className="p-3 rounded-lg border border-slate-800 bg-slate-950 flex items-center justify-between text-xs">
                <div>
                  <span className="font-semibold text-slate-200 block">Bangladesh Bank Official Media Room</span>
                  <span className="text-[11px] text-slate-500 font-mono block mt-0.5">
                    https://www.bb.org.bd/en/index.php/mediaroom/circular
                  </span>
                </div>
                <div className="text-right">
                  <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-mono">
                    CONNECTED
                  </span>
                  <span className="text-[10px] text-slate-500 block font-mono mt-1">Interval: 3.0s</span>
                </div>
              </div>
            </div>
          </div>

          {/* Catalog Review List */}
          <div className="border border-slate-800 bg-slate-900/40 rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-white uppercase tracking-wider font-mono">
                Recent Ingested Publications ({documents.length})
              </h2>
            </div>

            <div className="space-y-2.5 max-h-[460px] overflow-y-auto">
              {documents.length === 0 ? (
                <p className="text-xs text-slate-500 py-4 text-center">No publications in database yet.</p>
              ) : (
                documents.map((d) => (
                  <div
                    key={d.id}
                    className="p-3 rounded-lg border border-slate-800/80 bg-slate-950 flex items-center justify-between text-xs"
                  >
                    <div className="pr-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-brand-400 font-semibold text-[11px]">
                          {d.reference_number || "BB Circular"}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {d.publication_date}
                        </span>
                      </div>
                      <p className="text-slate-300 font-medium mt-0.5 line-clamp-1">{d.title}</p>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className="px-2 py-0.5 rounded bg-slate-900 text-slate-400 font-mono text-[10px] border border-slate-800">
                        {d.versions?.[0]?.page_count || 0} pgs
                      </span>
                      <a
                        href={`http://localhost:8000/api/v1/documents/${d.id}/pdf`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-brand-400 hover:text-brand-300 font-mono"
                      >
                        PDF ↗
                      </a>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
