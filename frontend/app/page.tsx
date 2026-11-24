"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Bookmark, CalendarDays, CalendarRange, FileSearch, Search, Sun, X } from "lucide-react";
import {
  AUTH_CHANGED_EVENT,
  AuthUser,
  DocumentItem,
  DocumentPage,
  Institution,
  fetchCurrentUser,
  fetchDocument,
  fetchDocumentPages,
  fetchInstitutions,
  getStoredUser,
  queryResearchAssistant,
  fetchResearchMatches,
  type ResearchCitation,
} from "@/services/api";
import { pageCorrected } from "@/services/claimsStore";
import AccountModal from "@/components/AccountModal";
import MyCircularUpload from "@/components/MyCircularUpload";
import CircularDetail, { QaResponse } from "@/components/CircularDetail";
import type { PageHighlight } from "@/components/PagePanel";
import StatusBadge, { InForceBadge, PrivateTag } from "@/components/StatusBadge";
import { inForceOf, seedDocuments, useRelState } from "@/services/relationshipsStore";
import { SEARCH_INPUT_ID } from "@/components/AppHeader";
import { EASE_OUT, EmptyState, Notice, SkeletonLine, titleWithoutRef } from "@/components/ui";
import DashboardAsk from "@/components/DashboardAsk";
import AssignedPanel from "@/components/AssignedPanel";
import { QuickSave } from "@/components/SaveButtons";
import { fetchFeed, fetchFeedCounts, fetchTopicNames, type Choice, type FeedCounts, type Period } from "@/services/libraryApi";
import { useLists } from "@/services/listsStore";

const PAGE_SIZE = 30;
type Box = Period | "later";
const BOXES: { id: Box; label: string; hint: string; Icon: typeof Sun }[] = [
  { id: "today", label: "Today", hint: "Issued today", Icon: Sun },
  { id: "week", label: "This week", hint: "Since Sunday", Icon: CalendarDays },
  { id: "month", label: "This month", hint: "Since the 1st", Icon: CalendarRange },
  { id: "later", label: "Read later", hint: "Saved by you", Icon: Bookmark },
];

/** "Expected credit loss (ECL)" -> "Expected credit loss", for the small tags on list rows. */
function shortTopic(label: string) {
  return label.replace(/ \(.*\)$/, "");
}

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
  const boxParam = searchParams.get("box");
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
  const [topic, setTopic] = useState("ALL");
  const [filterTab, setFilterTab] = useState<"dept" | "topic">("dept");
  const [box, setBox] = useState<Box | null>(() => (["today", "week", "month", "later"].includes(boxParam || "") ? (boxParam as Box) : null));
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [counts, setCounts] = useState<FeedCounts | null>(null);
  const [topicNames, setTopicNames] = useState<Record<string, string>>({});
  const feedRequest = useRef(0);
  const lists = useLists();

  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);
  const [docPages, setDocPages] = useState<DocumentPage[]>([]);
  const selectedDocIdRef = useRef<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [pagePanelOpen, setPagePanelOpen] = useState(false);
  const [highlight, setHighlight] = useState<PageHighlight | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  // Set when a register item opened an older version of the circular: its pages are shown instead of the current ones.
  const [viewVersion, setViewVersion] = useState<string | null>(null);
  const viewVersionRef = useRef<string | null>(null);
  viewVersionRef.current = viewVersion;


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
  const openedByLink = useRef(false);
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

    // The checked points are read and kept fresh by the circular page itself (services/claimsStore.ts).
  };

  const feedQuery = (offset: number) => ({
    period: box && box !== "later" ? box : null,
    saved: box === "later" ? ("READ_LATER" as const) : null,
    department: filterTab === "dept" && dept !== "ALL" ? dept : null,
    topic: filterTab === "topic" && topic !== "ALL" ? topic : null,
    q: search.trim(),
    limit: PAGE_SIZE,
    offset,
  });

  const loadCounts = () => {
    fetchFeedCounts()
      .then(setCounts)
      .catch(() => undefined);
  };

  const loadMore = async () => {
    const id = feedRequest.current;
    setLoadingMore(true);
    try {
      const page = await fetchFeed(feedQuery(documents.length));
      if (id !== feedRequest.current) return;
      seedDocuments(page.items);
      setDocuments((prev) => [...prev, ...page.items.filter((d) => !prev.some((p) => p.id === d.id))]);
      setTotal(page.total);
    } catch (err: any) {
      if (id === feedRequest.current) setLoadError(err.message || "Could not load more circulars.");
    } finally {
      if (id === feedRequest.current) setLoadingMore(false);
    }
  };

  const loadData = async () => {
    const id = ++feedRequest.current;
    try {
      setLoading(true);
      setLoadError(null);
      const [page, insts] = await Promise.all([fetchFeed(feedQuery(0)), institutions.length ? Promise.resolve(institutions) : fetchInstitutions()]);
      if (id !== feedRequest.current) return;
      const docs = page.items;
      setDocuments(docs);
      setTotal(page.total);
      seedDocuments(docs);
      setInstitutions(insts);
      if (!selectedDoc && !deepLinkRequested.current && docs.length > 0 && typeof window !== "undefined" && window.innerWidth >= 1024) {
        handleSelectDoc(docs[0]);
      }
    } catch (err: any) {
      if (id === feedRequest.current) setLoadError(err.message || "Failed to load circulars from the backend.");
    } finally {
      if (id === feedRequest.current) setLoading(false);
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

  // Reload when a filter, the search or the signed-in user changes, so private circulars appear or disappear.
  useEffect(() => {
    const t = window.setTimeout(loadData, search ? 250 : 0);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, box, dept, topic, filterTab, currentUser?.id]);

  // The numbers on the boxes: on load, when the person changes, and whenever a saved list changes
  // (a bookmark tapped anywhere updates the Read later box at once). The Read later list itself is
  // re-read too while it is the one showing.
  useEffect(() => {
    loadCounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser?.id, lists.version]);
  useEffect(() => {
    if (box === "later" && lists.version > 0) loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lists.version]);
  useEffect(() => {
    fetchTopicNames()
      .then((t) => setTopicNames(Object.fromEntries(t.map((c) => [c.code, c.label]))))
      .catch(() => undefined);
  }, []);

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
        openedByLink.current = true;
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
      // A link opened while the page is still loading jumps straight there: a smooth scroll is cut short then.
      if (el && window.innerWidth < 1024) el.scrollIntoView({ behavior: openedByLink.current ? "auto" : "smooth", block: "start" });
    };
    const t1 = window.setTimeout(go, 90);
    // Again once the row above has finished collapsing.
    const t2 = window.setTimeout(() => {
      go();
      // A link opened before the list arrived: keep the wish until the list (which sits above it) and the row exist.
      if (!loading && (document.getElementById(`circular-${id}`) || document.getElementById("circular-standalone"))) {
        wantScroll.current = false;
        openedByLink.current = false;
      }
    }, 420);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDoc?.id, loading]);

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

  // The server does the filtering; while a bookmark is being taken off, the row leaves the Read later list at once.
  const laterList = lists.lists.find((l) => l.kind === "READ_LATER");
  const filtered = box === "later" && laterList ? documents.filter((d) => laterList.document_ids.includes(d.id)) : documents;
  const boxCount = (b: Box) => (counts ? (b === "later" ? (laterList ? laterList.document_ids.length : counts.read_later) : counts[b]) : null);
  const chips: Choice[] =
    filterTab === "dept" ? (counts?.departments ?? []).slice(0, 14) : (counts?.topics ?? []).slice().sort((a, b) => b.count - a.count);
  const activeChip = filterTab === "dept" ? dept : topic;
  const setChip = (code: string) => (filterTab === "dept" ? setDept(code) : setTopic(code));

  // The circulars before and after the open one in the list, for the arrows and the J / K keys.
  const openIdx = selectedDoc ? filtered.findIndex((d) => d.id === selectedDoc.id) : -1;
  const stepTo = (d: DocumentItem | undefined) =>
    d ? { label: d.reference_number || titleWithoutRef(d.title, d.reference_number), open: () => handleSelectDoc(d) } : null;
  const prevDoc = openIdx > 0 ? stepTo(filtered[openIdx - 1]) : null;
  const nextDoc = openIdx >= 0 && openIdx < filtered.length - 1 ? stepTo(filtered[openIdx + 1]) : null;
  const stepRef = useRef<{ prev: typeof prevDoc; next: typeof nextDoc }>({ prev: null, next: null });
  stepRef.current = { prev: prevDoc, next: nextDoc };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) return;
      if (document.querySelector('[role="dialog"]')) return;
      if (e.key === "j") stepRef.current.next?.open();
      else if (e.key === "k") stepRef.current.prev?.open();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Phones: the source page opens as a sheet over the page, so the page behind it must not scroll.
  useEffect(() => {
    if (!pagePanelOpen || window.innerWidth >= 1280) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [pagePanelOpen]);

  // Wide screens: while the source page is open the list steps aside, so the page has room to be read.
  const [wide, setWide] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1280px)");
    const on = () => setWide(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  const focusReading = wide && pagePanelOpen && !!selectedDoc;

  const renderDetail = (doc: DocumentItem, inRow = false) => (
    <>
      {detailError && (
        <Notice kind="error" className="mb-3">
          {detailError}
        </Notice>
      )}
      <CircularDetail
        doc={doc}
        viewingVersionId={viewVersion}
        pages={docPages}
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
        inRow={inRow}
        prevDoc={prevDoc}
        nextDoc={nextDoc}
        onPageSaved={(saved) => {
          setDocPages((prev) => prev.map((p) => (p.id === saved.id ? { ...p, ...saved } : p)));
          pageCorrected(doc.id, undefined, saved);
        }}
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

      {/* Page heading */}
      <div>
        <h1 className="text-[26px] font-semibold tracking-[-0.015em] text-ink">Dashboard</h1>
        <p className="mt-0.5 text-[14.5px] text-ink-3">Bangladesh Bank circulars, newest first. Tap a box to see only those.</p>
      </div>

      {/* Today / This week / This month / Read later */}
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {BOXES.map(({ id, label, hint, Icon }) => {
          const active = box === id;
          const n = boxCount(id);
          const locked = id === "later" && !currentUser;
          return (
            <button
              key={id}
              type="button"
              onClick={() => {
                if (locked) return setAccountOpen(true);
                setBox(active ? null : id);
                // Show the result: the list starts below the question box and the filters.
                if (!active) {
                  requestAnimationFrame(() =>
                    document.getElementById("circular-list-heading")?.scrollIntoView({ behavior: "smooth", block: "start" }),
                  );
                }
              }}
              aria-pressed={active}
              className={`group rounded-panel border px-3.5 py-3 text-left transition-colors ${
                active ? "border-accent bg-accent-soft" : "border-line bg-surface hover:border-accent/50"
              }`}
            >
              <span className="flex items-center justify-between">
                <span className={`text-[13.5px] font-semibold ${active ? "text-accent" : "text-ink-2"}`}>{label}</span>
                <Icon className={`h-4 w-4 ${active ? "text-accent" : "text-ink-3"}`} strokeWidth={1.75} />
              </span>
              <span className="mt-1 block text-[28px] font-semibold leading-none tracking-tight text-ink tabular-nums">
                {locked ? "-" : n === null ? <SkeletonLine className="mt-1 h-6 w-10" /> : n}
              </span>
              <span className="mt-1.5 block text-[12px] text-ink-3">{locked ? "Register to save" : hint}</span>
            </button>
          );
        })}
      </div>

      {currentUser && <AssignedPanel userId={currentUser.id} />}

      <DashboardAsk signedIn={!!currentUser} onSignIn={() => setAccountOpen(true)} />

      {/* Search and filters */}
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="inline-flex shrink-0 self-start rounded-control bg-sunken p-0.5" role="tablist" aria-label="Filter by">
          {(
            [
              { id: "dept", label: "Departments" },
              { id: "topic", label: "Categories" },
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={filterTab === t.id}
              onClick={() => setFilterTab(t.id)}
              className={`rounded-[7px] px-3.5 py-1.5 text-[13.5px] font-semibold transition-colors ${
                filterTab === t.id ? "bg-surface text-ink shadow-sm" : "text-ink-3 hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="relative w-full md:w-[24rem]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-3" strokeWidth={1.75} />
          <label htmlFor={SEARCH_INPUT_ID} className="sr-only">
            Search circulars
          </label>
          <input
            id={SEARCH_INPUT_ID}
            type="search"
            placeholder="Search number, title or words inside (e.g. ECL)"
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

      <div role="tablist" aria-label={filterTab === "dept" ? "Filter by department" : "Filter by category"} className="-mx-1 -mt-2 flex gap-1 overflow-x-auto px-1 pb-1">
        {[{ code: "ALL", label: "All", count: -1 }, ...chips].map((d) => {
          const active = activeChip === d.code;
          const label = filterTab === "topic" && d.code !== "ALL" ? shortTopic(topicNames[d.code] || d.label) : d.label;
          return (
            <button
              key={`${filterTab}-${d.code}`}
              role="tab"
              aria-selected={active}
              type="button"
              onClick={() => setChip(d.code)}
              className={`relative shrink-0 whitespace-nowrap rounded-full px-3.5 py-1.5 text-[13.5px] font-semibold transition-colors ${
                active ? "text-accent-ink" : "text-ink-2 hover:bg-sunken hover:text-ink"
              }`}
            >
              {active && (
                <motion.span layoutId="dept-pill" className="absolute inset-0 rounded-full bg-accent" transition={{ type: "spring", stiffness: 500, damping: 40 }} />
              )}
              <span className="relative">
                {label}
                {d.count > 0 && <span className={`ml-1.5 text-[12px] tabular-nums ${active ? "opacity-80" : "text-ink-3"}`}>{d.count}</span>}
              </span>
            </button>
          );
        })}
      </div>

      <div id="circular-list-heading" className="-mt-2 flex scroll-mt-20 flex-wrap items-center gap-2 text-[13px] text-ink-3" aria-live="polite">
        {box && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft py-1 pl-3 pr-1 text-[13.5px] font-semibold text-accent">
            {BOXES.find((b) => b.id === box)?.hint}
            <button
              type="button"
              onClick={() => setBox(null)}
              aria-label="Show all circulars"
              className="grid h-5 w-5 place-items-center rounded-full hover:bg-accent/15"
            >
              <X className="h-3.5 w-3.5" strokeWidth={2.25} />
            </button>
          </span>
        )}
        <span>
          {loading ? "Loading..." : `${total} ${total === 1 ? "circular" : "circulars"}${box || search || activeChip !== "ALL" ? (total === 1 ? " matches" : " match") : " in the library"}`}
        </span>
      </div>

      <div className={`grid grid-cols-1 gap-6 ${focusReading ? "" : "lg:grid-cols-[minmax(300px,360px)_minmax(0,1fr)]"}`}>
        {/* List */}
        <div className={`space-y-3 lg:sticky lg:top-[72px] lg:max-h-[calc(100dvh-88px)] lg:self-start lg:overflow-y-auto lg:pr-1 ${focusReading ? "lg:hidden" : ""}`}>
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
          ) : documents.length === 0 && !search && !box && activeChip === "ALL" ? (
            <EmptyState title="No circulars yet" icon={<FileSearch className="h-6 w-6" strokeWidth={1.5} />}>
              Circulars appear here once an administrator approves them from the review queue or uploads a PDF.
            </EmptyState>
          ) : filtered.length === 0 ? (
            <EmptyState title="Nothing matches" icon={<Search className="h-6 w-6" strokeWidth={1.5} />}>
              {box === "later" ? "Tap the bookmark on any circular to keep it here for later." : <>Try a circular number such as &ldquo;BRPD 12&rdquo;, a different word, or the All filter.</>}
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
                    className="relative scroll-mt-[72px] border-b border-line last:border-0"
                  >
                    {/* Star and bookmark sit beside the row button (a button cannot hold other buttons). */}
                    <span className="absolute right-2.5 top-2 z-10">
                      <QuickSave documentId={doc.id} size="sm" onNeedSignIn={() => setAccountOpen(true)} />
                    </span>
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
                          <span className="shrink-0 pr-[60px] text-[12.5px] text-ink-3 tabular-nums">{shortDate(doc.publication_date)}</span>
                        </span>
                        <span className="mt-1.5 line-clamp-3 block text-[14.5px] font-medium leading-snug text-ink">{titleWithoutRef(doc.title, doc.reference_number)}</span>
                        {doc.topics && doc.topics.length > 0 && (
                          <span className="mt-1.5 flex flex-wrap gap-1">
                            {doc.topics.filter((t) => t !== "OTHER").slice(0, 3).map((t) => (
                              <span key={t} className="rounded-full bg-sunken px-2 py-0.5 text-[11.5px] font-medium text-ink-2">
                                {shortTopic(topicNames[t] || t)}
                              </span>
                            ))}
                          </span>
                        )}
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
                          <div className="p-2 sm:p-3">{renderDetail(doc, true)}</div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.li>
                );
              })}
            </ul>
          )}
          {!loading && documents.length > 0 && documents.length < total && (
            <button type="button" onClick={loadMore} disabled={loadingMore} className="btn-secondary w-full">
              {loadingMore ? "Loading..." : `Show more (${total - documents.length} left)`}
            </button>
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
