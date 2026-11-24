import type { Metadata } from "next";
import Link from "next/link";
import { notFound, permanentRedirect } from "next/navigation";
import { ArrowRight, CheckCircle2, Eye, FileText } from "lucide-react";
import { SITE_URL, serverApi } from "@/services/serverApi";

/**
 * A circular's public page: rendered on the server so search engines and shared links see the real content
 * (SEO, approved 2026-11-24). The interactive reader (source pages with highlights, Ask, mind map) stays at
 * /dashboard?doc=<id>; every point here links to its page there.
 */

interface Point {
  text: string;
  page?: number | null;
  verified: boolean;
}
interface PublicCircular {
  id: string;
  path: string;
  indexable: boolean;
  reference_number?: string | null;
  title: string;
  title_bn?: string | null;
  department: string;
  publication_date?: string | null;
  status_label?: string | null;
  summary: Point[];
  changes: Point[];
  requirements: Point[];
  dates: Point[];
  applies_to: Point[];
  exemptions: Point[];
  pages: number;
}

type Params = { params: { dept: string; slug: string } };

async function load(dept: string, slug: string): Promise<PublicCircular | null> {
  const res = await fetch(serverApi(`/public/circulars/${encodeURIComponent(dept)}/${encodeURIComponent(slug)}`), {
    next: { revalidate: 600 },
  }).catch(() => null);
  if (!res || res.status === 404) return null;
  if (!res.ok) throw new Error(`Could not load the circular (${res.status})`);
  return res.json();
}

function longDate(value?: string | null) {
  if (!value) return "";
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
}

function description(c: PublicCircular) {
  const first = c.summary[0]?.text || c.requirements[0]?.text || c.title;
  const text = `${c.reference_number ? `${c.reference_number}, ` : ""}${longDate(c.publication_date)}. ${first}`;
  return text.length > 158 ? `${text.slice(0, 155).trimEnd()}…` : text;
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const c = await load(params.dept, params.slug);
  if (!c) return { title: "Circular not found | Amar Circular", robots: { index: false } };
  const title = `${c.reference_number ? `${c.reference_number}: ` : ""}${c.title} | Amar Circular`;
  const desc = description(c);
  const url = `${SITE_URL}${c.path}`;
  return {
    title,
    description: desc,
    alternates: { canonical: url },
    robots: c.indexable ? { index: true, follow: true } : { index: false, follow: true },
    openGraph: { type: "article", url, title, description: desc, siteName: "Amar Circular", publishedTime: c.publication_date ?? undefined },
    twitter: { card: "summary", title, description: desc },
  };
}

const SECTIONS: { key: keyof Pick<PublicCircular, "summary" | "changes" | "requirements" | "applies_to" | "dates" | "exemptions">; title: string }[] = [
  { key: "summary", title: "Summary" },
  { key: "changes", title: "What has changed" },
  { key: "requirements", title: "Requirements" },
  { key: "applies_to", title: "Who it applies to" },
  { key: "dates", title: "Dates" },
  { key: "exemptions", title: "Exceptions" },
];

export default async function CircularPage({ params }: Params) {
  const c = await load(params.dept, params.slug);
  if (!c) notFound();
  if (c.path !== `/circular/${params.dept}/${params.slug}`) permanentRedirect(c.path);

  const reader = `/dashboard?doc=${c.id}`;
  const any = SECTIONS.some((s) => c[s.key].length > 0);
  const verified = c.status_label === "AI verified";
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: `${c.reference_number ? `${c.reference_number}: ` : ""}${c.title}`.slice(0, 110),
    datePublished: c.publication_date ?? undefined,
    inLanguage: "en",
    mainEntityOfPage: `${SITE_URL}${c.path}`,
    publisher: { "@type": "Organization", name: "Amar Circular", url: SITE_URL },
    about: "Bangladesh Bank circular",
  };

  return (
    <article className="mx-auto max-w-[820px] py-2 sm:py-6">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />

      <nav aria-label="Breadcrumb" className="mb-5 text-[13px] text-ink-3">
        <ol className="flex flex-wrap items-center gap-1.5">
          <li>
            <Link href="/" className="hover:text-ink">
              Home
            </Link>
          </li>
          <li aria-hidden>›</li>
          <li>
            <Link href="/dashboard" className="hover:text-ink">
              Library
            </Link>
          </li>
          <li aria-hidden>›</li>
          <li>{c.department}</li>
          <li aria-hidden>›</li>
          <li className="font-semibold text-ink-2">{c.reference_number || "Circular"}</li>
        </ol>
      </nav>

      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="font-semibold text-accent">{c.reference_number || "Circular"}</span>
          {c.status_label && (
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-semibold ${
                verified ? "bg-ok-soft text-ok" : "bg-info-soft text-info"
              }`}
            >
              {verified ? <CheckCircle2 className="h-3 w-3" aria-hidden /> : <Eye className="h-3 w-3" aria-hidden />}
              {c.status_label}
            </span>
          )}
          <span className="text-ink-3">
            {longDate(c.publication_date)}
            {c.pages > 0 && ` · ${c.pages} page${c.pages === 1 ? "" : "s"}`}
          </span>
        </div>
        <h1 className="font-serif text-[30px] font-medium leading-[1.15] text-ink sm:text-[38px]">{c.title}</h1>
        {c.title_bn && (
          <p lang="bn" className="font-bangla text-[17px] text-ink-2">
            {c.title_bn}
          </p>
        )}
        <div className="flex flex-wrap gap-3 pt-1">
          <Link href={reader} className="btn-primary h-11 px-5 text-[15px]">
            <FileText className="h-4 w-4" aria-hidden /> Open with source pages
          </Link>
          <Link href={`/circular/${c.id}/links`} className="btn-secondary h-11 px-5 text-[15px]">
            History &amp; links
          </Link>
        </div>
      </header>

      {any ? (
        <div className="mt-8 space-y-8">
          {SECTIONS.filter((s) => c[s.key].length > 0).map((s) => (
            <section key={s.key} aria-labelledby={`s-${s.key}`}>
              <h2 id={`s-${s.key}`} className="text-[18px] font-bold text-ink">
                {s.title}
              </h2>
              <ul className="mt-3 space-y-3">
                {c[s.key].map((p, i) => (
                  <li key={i} className="rounded-[12px] border border-line bg-surface px-4 py-3">
                    <p className="text-[15.5px] leading-relaxed text-ink">{p.text}</p>
                    {p.page ? (
                      <Link
                        href={`${reader}&page=${p.page}`}
                        className="mt-2 inline-flex items-center gap-1 text-[13px] font-semibold text-accent hover:underline"
                      >
                        Page {p.page} · {p.verified ? "AI verified" : "AI draft"} <ArrowRight className="h-3 w-3" aria-hidden />
                      </Link>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <div className="mt-8 rounded-[14px] border border-line bg-surface px-5 py-5">
          <p className="text-[16px] font-semibold text-ink">Summary not ready yet</p>
          <p className="mt-1 text-[15px] leading-relaxed text-ink-2">
            This circular has not been analysed yet. Its original pages can be read and searched in the reader.
          </p>
          <Link href={reader} className="btn-primary mt-4 h-10 px-4">
            Read the original
          </Link>
        </div>
      )}

      <p className="mt-10 border-t border-line pt-4 text-[13px] text-ink-3">
        Source: Bangladesh Bank. Each point links to the page of the original circular it comes from.
      </p>
    </article>
  );
}
