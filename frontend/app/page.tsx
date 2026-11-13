"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { FileSearch, Search, X } from "lucide-react";
import {
  AUTH_CHANGED_EVENT,
  AuthUser,
  DocumentAnalysisData,
  DocumentItem,
  DocumentPage,
  Institution,
  ObligationItem,
  RelationshipItem,
  fetchCurrentUser,
  fetchDocument,
  fetchDocumentAnalysis,
  fetchDocumentObligations,
  fetchDocumentPages,
  fetchDocumentRelationships,
  fetchDocuments,
  fetchInstitutions,
  getStoredUser,
  queryResearchAssistant,
  fetchResearchMatches,
  type ResearchCitation,
} from "@/services/api";
import AccountModal from "@/components/AccountModal";
import MyCircularUpload from "@/components/MyCircularUpload";
import CircularDetail, { QaResponse } from "@/components/CircularDetail";
import type { PageHighlight } from "@/components/PagePanel";
import StatusBadge, { InForceBadge, PrivateTag } from "@/components/StatusBadge";
import { inForceOf, seedDocuments, useRelState } from "@/services/relationshipsStore";
import { SEARCH_INPUT_ID } from "@/components/AppHeader";
import { EASE_OUT, EmptyState, Notice, SkeletonLine, titleWithoutRef } from "@/components/ui";

const DEPARTMENTS = [
  { code: "ALL", label: "All" },
  { code: "BRPD", label: "BRPD" },
  { code: "DOS", label: "DOS" },
  { code: "FEPD", label: "FEPD" },
  { code: "PSD", label: "PSD" },
  { code: "SMESPD", label: "SMESPD" },
];

function shortDate(value?: string) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function CircularsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const docParam = searchParams.get("doc");
  const pageParam = searchParams.get("page");
  const versionParam = searchParams.get("version");
  const rel = useRelState();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("ALL");

  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [docPages, setDocPages] = useState<DocumentPage[]>([]);
  const selectedDocIdRef = useRef<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pagePanelOpen, setPagePanelOpen] = useState(false);
  const [highlight, setHighlight] = useState<PageHighlight | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  // Set when a register item opened an older version of the circular: its pages are shown instead of the current ones.
  const [viewVersion, setViewVersion] = useState<string | null>(null);
  const viewVersionRef = useRef<string | null>(null);
  viewVersionRef.current = viewVersion;

  const [analysis, setAnalysis] = useState<DocumentAnalysisData | null>(null);
  const [obligations, setObligations] = useState<ObligationItem[]>([]);
  const [relationships, setRelationships] = useState<RelationshipItem[]>([]);

  const [qaQuery, setQaQuery] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaResponse, setQaResponse] = useState<QaResponse | null>(null);
  const [qaMatches, setQaMatches] = useState<ResearchCitation[] | null>(null);
  const qaAskId = useRef(0);
  const [qaError, setQaError] = useState<string | null>(null);

  // Ignores answers for a circular the user has already moved away from.
  const selectionToken = useRef(0);
  // True when the page was opened by a "?doc=<id>&page=<n>" link, so the first-circular default never overrides it.
  const deepLinkRequested = useRef(false);
  // Latest values for effects that must not re-run when they change.
  const selectedRef = useRef<DocumentItem | null>(null);
  const pageNumberRef = useRef(1);
  const panelOpenRef = useRef(false);
  // Set when a circular was just opened at phone width, so its detail is scrolled into view.
  const wantScroll = useRef(false);
  selectedRef.current = selectedDoc;
  pageNumberRef.current = pageNumber;
  panelOpenRef.current = pagePanelOpen;

  useEffect(() => {
    // Show the cached user immediately, then confirm the role with GET /auth/me.
    setCurrentUser(getStoredUser());
    fetchCurrentUser()
      .then((u) => setCurrentUser(u))
      .catch(() => setCurrentUser(getStoredUser()));
    const onAuthChanged = () => setCurrentUser(getStoredUser());
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
    return () => window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
  }, []);

  const handleSelectDoc = async (doc: DocumentItem, version?: string | null) => {
    const token = ++selectionToken.current;
    if (typeof window !== "undefined" && window.innerWidth < 1024) wantScroll.current = true;
    setSelectedDoc(doc);
    selectedDocIdRef.current = doc.id;
    setPageNumber(1);
    setHighlight(null);
    setQaResponse(null);
    setQaMatches(null);
    setQaError(null);
    setDetailError(null);
    setDetailLoading(true);
    const older = version && version !== doc.current_version_id ? version : null;
    setViewVersion(older);

    if (older || (doc.versions && doc.versions.length > 0)) {
      // The current version is the one the analysis and its quotes point at, unless a link asked for an older one.
      fetchDocumentPages(doc.id, older || doc.current_version_id || doc.versions[0].id)
        .then((pages) => token === selectionToken.current && setDocPages(pages))
        .catch(() => token === selectionToken.current && setDocPages([]));
    } else {
      setDocPages([]);
    }

    try {
      const [aiData, obls, rels] = await Promise.all([
        fetchDocumentAnalysis(doc.id).catch(() => null),
        fetchDocumentObligations(doc.id).catch(() => []),
        fetchDocumentRelationships(doc.id).catch(() => []),
      ]);
      if (token !== selectionToken.current) return;
      setAnalysis(aiData);
      setObligations(obls);
      setRelationships(rels);
    } catch (err: any) {
      if (token === selectionToken.current) setDetailError(err.message || "Could not load this circular's analysis.");
    } finally {
      if (token === selectionToken.current) setDetailLoading(false);
    }
  };

  const loadData = async () => {
    try {
      setLoading(true);
      setLoadError(null);
      const [docs, insts] = await Promise.all([fetchDocuments({ search, corpus_type: "GENUINE" }), fetchInstitutions()]);
      setDocuments(docs);
      seedDocuments(docs);
      setInstitutions(insts);
      if (!selectedDoc && !deepLinkRequested.current && docs.length > 0 && typeof window !== "undefined" && window.innerWidth >= 1024) {
        handleSelectDoc(docs[0]);
      }
    } catch (err: any) {
      setLoadError(err.message || "Failed to load circulars from the backend.");
    } finally {
      setLoading(false);
    }
  };

  // Pages waiting to be read from the page image fill in by themselves: while any page waits,
  // the page list is re-read every few seconds and the new text shows the moment it is stored.
  const waitingPages = docPages.some((p) => p.quality_status === "PENDING_VISION");
  useEffect(() => {
    if (!selectedDoc || !waitingPages) return;
    const versionId = viewVersion || selectedDoc.current_version_id || selectedDoc.versions?.[0]?.id;
    if (!versionId) return;
    const docId = selectedDoc.id;
    const timer = window.setInterval(() => {
      fetchDocumentPages(docId, versionId)
        .then((pages) => {
          if (selectedDocIdRef.current === docId) setDocPages(pages);
        })
        .catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [selectedDoc, viewVersion, waitingPages]);

  // Re-reads one document after an admin action so its status badge is current.
  const refreshDocument = async (doc: DocumentItem) => {
    try {
      const fresh = await fetchDocument(doc.id);
      seedDocuments([fresh]);
      setDocuments((prev) => prev.map((d) => (d.id === fresh.id ? fresh : d)));
      await handleSelectDoc(fresh);
    } catch (err: any) {
      setLoadError(err.message || "Failed to refresh the document.");
    }
  };

  // Reload when the search or the signed-in user changes, so private circulars appear or disappear.
  useEffect(() => {
    const t = window.setTimeout(loadData, search ? 250 : 0);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, currentUser?.id]);

  // Opens "/?doc=<id>&page=<n>" (search results, links from other screens, a refresh): the circular, with its
  // source page showing. The same address then stays in the bar while the circular is open.
  useEffect(() => {
    if (!docParam) return;
    const wanted = parseInt(pageParam || "", 10);
    const hasPage = Number.isFinite(wanted) && wanted > 0;
    deepLinkRequested.current = true;
    if (selectedRef.current?.id === docParam) {
      const wantVersion = versionParam && versionParam !== selectedRef.current.current_version_id ? versionParam : null;
      if (wantVersion !== viewVersionRef.current) {
        handleSelectDoc(selectedRef.current, wantVersion);
        if (hasPage) {
          setPageNumber(wanted);
          setPagePanelOpen(true);
        }
        return;
      }
      if (hasPage && (pageNumberRef.current !== wanted || !panelOpenRef.current)) {
        setPageNumber(wanted);
        setPagePanelOpen(true);
      }
      return;
    }
    let alive = true;
    fetchDocument(docParam)
      .then((doc) => {
        if (!alive) return;
        seedDocuments([doc]);
        handleSelectDoc(doc, versionParam);
        if (hasPage) {
          setPageNumber(wanted);
          setPagePanelOpen(true);
        }
      })
      .catch((err: any) => alive && setLoadError(err.message || "Could not open that circular."));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docParam, pageParam, versionParam]);

  // Keeps the address in step with what is open, without adding history entries (the back button still leaves the page).
  useEffect(() => {
    if (!selectedDoc) return;
    const p = new URLSearchParams();
    p.set("doc", selectedDoc.id);
    if (pagePanelOpen) p.set("page", String(pageNumber));
    if (viewVersion) p.set("version", viewVersion);
    if (window.location.search !== `?${p.toString()}`) router.replace(`/?${p.toString()}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDoc?.id, pagePanelOpen, pageNumber, viewVersion]);

  // Phone width: after a circular opens (from a list tap or a link), bring its detail into view.
  useEffect(() => {
    if (!selectedDoc || !wantScroll.current) return;
    const id = selectedDoc.id;
    const go = () => {
      const el = document.getElementById(`circular-${id}`) ?? document.getElementById("circular-standalone");
      if (el && window.innerWidth < 1024) el.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    const t1 = window.setTimeout(go, 90);
    // Again once the row above has finished collapsing.
    const t2 = window.setTimeout(() => {
      go();
      wantScroll.current = false;
    }, 420);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDoc?.id]);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!qaQuery.trim() || !selectedDoc) return;
    const id = ++qaAskId.current;
    setQaLoading(true);
    setQaError(null);
    setQaResponse(null);
    setQaMatches(null);
    // Matching lines come from a local search and show at once; the written answer fills in after.
    fetchResearchMatches(qaQuery, selectedDoc.id)
      .then((m) => {
        if (id === qaAskId.current) setQaMatches(m);
      })
      .catch(() => undefined);
    try {
      const res = await queryResearchAssistant(qaQuery, selectedDoc.id);
      if (id === qaAskId.current) setQaResponse(res);
    } catch (err: any) {
      if (id === qaAskId.current) setQaError(err.message || "Failed to process question.");
    } finally {
      if (id === qaAskId.current) setQaLoading(false);
    }
  };

  const filtered = documents.filter((doc) => {
    if (dept === "ALL") return true;
    const ref = (doc.reference_number || "").toUpperCase();
    const title = (doc.title || "").toUpperCase();
    return ref.includes(dept) || title.includes(dept);
  });

  const renderDetail = (doc: DocumentItem) => (
    <>
      {detailError && (
        <Notice kind="error" className="mb-3">
          {detailError}
        </Notice>
      )}
      <CircularDetail
        doc={doc}
        viewingVersionId={viewVersion}
        analysis={analysis}
        obligations={obligations}
        relationships={relationships}
        pages={docPages}
        detailLoading={detailLoading}
        pageNumber={pageNumber}
        setPageNumber={setPageNumber}
        pagePanelOpen={pagePanelOpen}
        setPagePanelOpen={setPagePanelOpen}
        highlight={highlight}
        setHighlight={setHighlight}
        qaQuery={qaQuery}
        setQaQuery={setQaQuery}
        qaLoading={qaLoading}
        qaResponse={qaResponse}
        qaMatches={qaMatches}
        qaError={qaError}
        onAsk={handleAsk}
        currentUser={currentUser}
        onSignIn={() => setAccountOpen(true)}
        onRefresh={() => refreshDocument(doc)}
        onPageSaved={(saved) => setDocPages((prev) => prev.map((p) => (p.id === saved.id ? { ...p, ...saved } : p)))}
      />
    </>
  );

  return (
    <div className="space-y-5">
      <AccountModal
        isOpen={accountOpen}
        onClose={() => setAccountOpen(false)}
        currentUser={currentUser}
        onUserChange={(u) => {
          setCurrentUser(u);
          if (selectedDoc) handleSelectDoc(selectedDoc);
        }}
      />

      {/* Page heading and tools */}
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-[26px] font-semibold tracking-[-0.015em] text-ink">Circulars</h1>
          <p className="mt-0.5 text-[14.5px] text-ink-3">
            {loading ? "Loading the library..." : `${documents.length} ${documents.length === 1 ? "circular" : "circulars"} from Bangladesh Bank, newest first`}
          </p>
        </div>
        <div className="relative w-full md:w-[22rem]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} />
          <label htmlFor={SEARCH_INPUT_ID} className="sr-only">
            Search circulars
          </label>
          <input
            id={SEARCH_INPUT_ID}
            type="search"
            placeholder="Search by number, title or topic"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="field h-10 pl-9 pr-9"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 grid h-6 w-6 -translate-y-1/2 place-items-center rounded text-ink-3 hover:text-ink"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <div role="tablist" aria-label="Filter by department" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
        {DEPARTMENTS.map((d) => {
          const active = dept === d.code;
          return (
            <button
              key={d.code}
              role="tab"
              aria-selected={active}
              type="button"
              onClick={() => setDept(d.code)}
              className={`relative shrink-0 rounded-full px-3.5 py-1.5 text-[13.5px] font-semibold transition-colors ${
                active ? "text-accent-ink" : "text-ink-2 hover:bg-sunken hover:text-ink"
              }`}
            >
              {active && (
                <motion.span layoutId="dept-pill" className="absolute inset-0 rounded-full bg-accent" transition={{ type: "spring", stiffness: 500, damping: 40 }} />
              )}
              <span className="relative">{d.label}</span>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(300px,360px)_minmax(0,1fr)]">
        {/* List */}
        <div className="space-y-3 lg:sticky lg:top-[72px] lg:max-h-[calc(100dvh-88px)] lg:self-start lg:overflow-y-auto lg:pr-1">
          {currentUser && !currentUser.is_superuser && <MyCircularUpload institutions={institutions} onUploaded={loadData} />}

          {/* Phone and tablet: a circular opened by a link that is not in the list below still shows here. */}
          {selectedDoc && !filtered.some((d) => d.id === selectedDoc.id) && (
            <div id="circular-standalone" className="scroll-mt-[72px] lg:hidden">
              {renderDetail(selectedDoc)}
            </div>
          )}

          {loading && documents.length === 0 ? (
            <div className="rounded-panel border border-line bg-surface" aria-busy="true" aria-label="Loading circulars">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="space-y-2 border-b border-line px-4 py-3.5 last:border-0">
                  <SkeletonLine className="h-3 w-40" />
                  <SkeletonLine className="h-3.5 w-full" />
                  <SkeletonLine className="h-3.5 w-3/4" />
                </div>
              ))}
            </div>
          ) : loadError ? (
            <Notice kind="error">
              <p className="font-semibold">Could not load circulars</p>
              <p className="mt-0.5 text-ink-2">{loadError}</p>
              <button type="button" onClick={loadData} className="btn-secondary mt-2 py-1">
                Try again
              </button>
            </Notice>
          ) : documents.length === 0 && !search ? (
            <EmptyState title="No circulars yet" icon={<FileSearch className="h-6 w-6" strokeWidth={1.5} />}>
              Circulars appear here once an administrator approves them from the review queue or uploads a PDF.
            </EmptyState>
          ) : filtered.length === 0 ? (
            <EmptyState title="Nothing matches" icon={<Search className="h-6 w-6" strokeWidth={1.5} />}>
              Try a circular number such as &ldquo;BRPD 12&rdquo;, a different word, or the All filter.
            </EmptyState>
          ) : (
            <ul className="overflow-hidden rounded-panel border border-line bg-surface">
              {filtered.map((doc, i) => {
                const isSelected = selectedDoc?.id === doc.id;
                const pageCount = doc.versions?.[0]?.page_count ?? 0;
                return (
                  <motion.li
                    key={doc.id}
                    id={`circular-${doc.id}`}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.22, delay: Math.min(i, 10) * 0.025, ease: EASE_OUT }}
                    className="scroll-mt-[72px] border-b border-line last:border-0"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        if (isSelected && typeof window !== "undefined" && window.innerWidth < 1024) {
                          setSelectedDoc(null);
                          router.replace("/", { scroll: false });
                          return;
                        }
                        handleSelectDoc(doc);
                      }}
                      aria-current={isSelected ? "true" : undefined}
                      className="group relative block w-full px-4 py-3.5 text-left"
                    >
                      {isSelected && (
                        <motion.span
                          layoutId="selected-row"
                          className="absolute inset-0 bg-accent-soft"
                          transition={{ type: "spring", stiffness: 500, damping: 42 }}
                        />
                      )}
                      <span className="absolute inset-0 bg-sunken opacity-0 transition-opacity group-hover:opacity-60" aria-hidden />
                      <span className="relative block">
                        <span className="flex items-center justify-between gap-2">
                          <span className="flex min-w-0 items-center gap-2">
                            <span className="refno truncate">{doc.reference_number || "Circular"}</span>
                            {doc.is_private && <PrivateTag />}
                          </span>
                          <span className="shrink-0 text-[12.5px] text-ink-3 tabular-nums">{shortDate(doc.publication_date)}</span>
                        </span>
                        <span className="mt-1.5 line-clamp-3 block text-[14.5px] font-medium leading-snug text-ink">{titleWithoutRef(doc.title, doc.reference_number)}</span>
                        <span className="mt-2.5 flex items-center justify-between gap-2">
                          <span className="shrink-0 whitespace-nowrap text-[12.5px] text-ink-3 tabular-nums">{pageCount > 0 ? `${pageCount} ${pageCount === 1 ? "page" : "pages"}` : "No pages yet"}</span>
                          <span className="flex min-w-0 flex-wrap items-center justify-end gap-1">
                            <InForceBadge info={inForceOf(rel, doc)} size="sm" plain />
                            <StatusBadge status={doc.publication_status} size="sm" />
                          </span>
                        </span>
                      </span>
                    </button>

                    {/* Phone and tablet: the circular opens right under its row. */}
                    <AnimatePresence initial={false}>
                      {isSelected && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.28, ease: EASE_OUT }}
                          className="overflow-hidden bg-sunken/60 lg:hidden"
                        >
                          <div className="p-2 sm:p-3">{renderDetail(doc)}</div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Desktop reading pane */}
        <div className="hidden min-w-0 lg:block">
          <AnimatePresence mode="wait">
            {selectedDoc ? (
              <motion.div
                key={selectedDoc.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, ease: EASE_OUT }}
              >
                {renderDetail(selectedDoc)}
              </motion.div>
            ) : (
              !loading &&
              !loadError &&
              documents.length > 0 && (
                <EmptyState title="Pick a circular" icon={<FileSearch className="h-6 w-6" strokeWidth={1.5} />}>
                  Choose one from the list to read its summary, requirements and source pages.
                </EmptyState>
              )
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export default function CircularsPage() {
  return (
    <Suspense fallback={null}>
      <CircularsPageInner />
    </Suspense>
  );
}
