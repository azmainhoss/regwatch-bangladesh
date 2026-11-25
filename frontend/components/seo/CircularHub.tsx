import Link from "next/link";
import { CheckCircle2 } from "lucide-react";
import { SITE_URL } from "@/services/serverApi";
import { type CircularList, type Hubs, longDate, refLabel } from "@/services/publicApi";

/**
 * A server-rendered list of circulars (one department, subject or year). Search engines read it as a normal page,
 * and every row links to the circular's own page.
 */
export function Breadcrumbs({ trail }: { trail: { name: string; href?: string }[] }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((t, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: t.name,
      ...(t.href ? { item: `${SITE_URL}${t.href}` } : {}),
    })),
  };
  return (
    <nav aria-label="Breadcrumb" className="mb-5 text-[13px] text-ink-3">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <ol className="flex flex-wrap items-center gap-1.5">
        {trail.map((t, i) => (
          <li key={i} className="flex items-center gap-1.5">
            {i > 0 && <span aria-hidden>›</span>}
            {t.href && i < trail.length - 1 ? (
              <Link href={t.href} className="hover:text-ink">
                {t.name}
              </Link>
            ) : (
              <span className={i === trail.length - 1 ? "font-semibold text-ink-2" : ""}>{t.name}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function CircularRows({ list, heading }: { list: CircularList; heading?: string }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    numberOfItems: list.items.length,
    itemListElement: list.items
      .filter((i) => i.analysed)
      .slice(0, 100)
      .map((i, n) => ({ "@type": "ListItem", position: n + 1, url: `${SITE_URL}${i.path}`, name: i.title })),
  };
  return (
    <section aria-label={heading || "Circulars"} className="mt-8">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      {heading && <h2 className="mb-3 text-[18px] font-bold text-ink">{heading}</h2>}
      <ul className="divide-y divide-line overflow-hidden rounded-[14px] border border-line bg-surface">
        {list.items.map((i) => (
          <li key={i.path}>
            <Link href={i.path} className="block px-4 py-3 hover:bg-sunken focus-visible:bg-sunken">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
                <span className="font-semibold text-accent">{refLabel(i.reference_number, i.publication_date) || i.department}</span>
                <span className="text-ink-3">{longDate(i.publication_date)}</span>
                {i.analysed && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-2 py-0.5 text-[12px] font-semibold text-ok">
                    <CheckCircle2 className="h-3 w-3" aria-hidden /> Summary
                  </span>
                )}
              </div>
              <p className="mt-1 text-[15.5px] leading-snug text-ink">{i.title}</p>
              {i.title_bn && (
                <p lang="bn" className="mt-0.5 font-bangla text-[14px] text-ink-3">
                  {i.title_bn}
                </p>
              )}
            </Link>
          </li>
        ))}
      </ul>
      {list.total > list.items.length && (
        <p className="mt-3 text-[13.5px] text-ink-3">
          Showing {list.items.length} of {list.total.toLocaleString("en")} circulars.{" "}
          <Link href="/dashboard" className="font-semibold text-accent hover:underline">
            Search all of them
          </Link>
          .
        </p>
      )}
    </section>
  );
}

/** Links to every department, subject and year page: the site's internal link map for crawlers and people. */
export function HubLinks({ hubs, skip }: { hubs: Hubs; skip?: string }) {
  const group = (title: string, base: string, items: { code: string; name: string; total: number }[], short?: boolean) => (
    <div>
      <h2 className="text-[16px] font-bold text-ink">{title}</h2>
      <ul className="mt-2 flex flex-wrap gap-2">
        {items
          .filter((h) => `${base}${h.code}` !== skip)
          .map((h) => (
            <li key={h.code}>
              <Link
                href={`${base}${h.code}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-[13.5px] text-ink-2 hover:border-accent hover:text-ink"
              >
                {short ? h.code.toUpperCase() : h.name}
                <span className="text-ink-3">{h.total.toLocaleString("en")}</span>
              </Link>
            </li>
          ))}
      </ul>
    </div>
  );
  return (
    <div className="mt-10 space-y-6 border-t border-line pt-6">
      {group("Circulars by department", "/circulars/", hubs.departments, true)}
      {group("Circulars by subject", "/circulars/topic/", hubs.topics)}
      {group("Circulars by year", "/circulars/", hubs.years)}
    </div>
  );
}
