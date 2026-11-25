import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SITE_URL } from "@/services/serverApi";
import { getHubs, getList } from "@/services/publicApi";
import { Breadcrumbs, CircularRows, HubLinks } from "@/components/seo/CircularHub";

// Rendered on request: at build time the backend may still be the old version.
export const dynamic = "force-dynamic";

const TITLE = "Latest Bangladesh Bank circulars (BRPD, FEPD, DOS, BFIU) | Amar Circular";
const DESC =
  "Every new Bangladesh Bank circular in one list, newest first, with a plain-English summary, deadlines and a link to the original PDF. বাংলাদেশ ব্যাংকের সর্বশেষ সার্কুলার।";

export const metadata: Metadata = {
  title: TITLE,
  description: DESC,
  alternates: { canonical: `${SITE_URL}/circulars` },
  openGraph: { type: "website", url: `${SITE_URL}/circulars`, title: TITLE, description: DESC, siteName: "Amar Circular" },
};

export default async function CircularsIndex() {
  const [hubs, latest] = await Promise.all([getHubs(), getList("latest", "all")]);
  if (!hubs || !latest) notFound();
  return (
    <div className="mx-auto max-w-[920px] py-2 sm:py-6">
      <Breadcrumbs trail={[{ name: "Home", href: "/" }, { name: "Circulars" }]} />
      <h1 className="font-serif text-[30px] font-medium leading-[1.15] text-ink sm:text-[40px]">Latest Bangladesh Bank circulars</h1>
      <p lang="bn" className="mt-1 font-bangla text-[17px] text-ink-2">
        বাংলাদেশ ব্যাংকের সর্বশেষ সার্কুলার ও প্রজ্ঞাপন
      </p>
      <p className="mt-3 max-w-[680px] text-[16px] leading-relaxed text-ink-2">
        {hubs.total.toLocaleString("en")} circulars from every Bangladesh Bank department, newest first. New circulars from
        bb.org.bd appear here within the hour. {hubs.analysed.toLocaleString("en")} of them are Ready, with a plain-English summary: what
        changed, what banks must do, deadlines, and the page of the original each point comes from.
      </p>
      <CircularRows list={latest} heading="Newest circulars" />
      <HubLinks hubs={hubs} />
    </div>
  );
}
