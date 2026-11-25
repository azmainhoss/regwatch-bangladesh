import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SITE_URL } from "@/services/serverApi";
import { bnDeptName, bnYear, getHubs, getList } from "@/services/publicApi";
import { Breadcrumbs, CircularRows, HubLinks } from "@/components/seo/CircularHub";

export const revalidate = 600;

/** What each department's circulars are about, in a line (unique text for each list page). */
const ABOUT: Record<string, string> = {
  brpd: "BRPD sets the core rules for scheduled banks: loan classification and provisioning, rescheduling and write-off, credit cards, large loans, governance, bank charges and branch rules.",
  fepd: "FEPD issues the foreign exchange rules: import and export payments, LCs, inward and outward remittance, remittance and cash incentives, foreign currency accounts and exchange houses.",
  feod: "FEOD handles foreign exchange operations: reporting and monitoring of import, export and remittance transactions.",
  dos: "DOS (Off-site Supervision) sets the returns and reports banks submit, stress testing, capital adequacy (Basel III) reporting and supervisory follow-up.",
  dfim: "DFIM regulates non-bank financial institutions (finance companies): their loans, provisioning, deposits, capital and governance.",
  psd: "PSD regulates payment systems: RTGS, BEFTN, NPSB, mobile financial services (MFS), digital banks, QR payments, PSOs and PSPs.",
  sfd: "SFD covers sustainable and green finance: green banking, climate risk, ESG and the related refinance schemes.",
  bfiu: "BFIU (Bangladesh Financial Intelligence Unit) issues the anti-money laundering and counter terrorist financing rules: KYC/CDD, STR and CTR reporting, CAMLCO duties and sanctions screening.",
  smespd: "SMESPD covers CMSME (SME) finance: SME loan targets, refinance and stimulus schemes, women entrepreneurs and startup funds.",
  acd: "ACD covers agricultural and rural credit: yearly agricultural loan targets, interest rates and refinance for farm loans.",
  acspd: "ACSPD covers agricultural credit and special programmes, including refinance and stimulus schemes for farm and rural borrowers.",
  dmd: "DMD covers government debt: treasury bills and bonds, savings instruments and how banks deal in them.",
  dcm: "DCM covers currency management: banknotes, soiled and mutilated notes, coins and cash handling at banks.",
  mpd: "MPD covers monetary policy: the policy rate, repo and reverse repo, CRR and SLR.",
  gbcsrd: "GBCSRD covered green banking and corporate social responsibility (CSR) by banks.",
  cib: "CIB (Credit Information Bureau) covers credit reports, CIB reporting by lenders and the rules for using CIB data.",
  fe: "FE circulars are the older series of foreign exchange rules, many still cited by newer FEPD circulars.",
};

type Params = { params: { code: string } };
const isYear = (code: string) => /^(19|20)\d{2}$/.test(code);

function titles(code: string, name: string) {
  if (isYear(code))
    return {
      h1: `Bangladesh Bank circulars ${code}`,
      bn: `বাংলাদেশ ব্যাংক সার্কুলার ${bnYear(code)}`,
      title: `Bangladesh Bank circulars ${code}: full list with summaries | Amar Circular`,
      desc: `All Bangladesh Bank circulars issued in ${code} (BRPD, FEPD, DOS, BFIU and more), newest first, with plain-English summaries, deadlines and the original PDF.`,
    };
  const short = code.toUpperCase();
  const bn = bnDeptName(short);
  return {
    h1: `${short} circulars`,
    bn: bn ? `${bn} সার্কুলার` : "",
    title: `${short} circulars ${new Date().getFullYear()}: full list with summaries and PDF | Amar Circular`,
    desc: `All ${short} circulars and circular letters of Bangladesh Bank${name === short ? "" : ` (${name})`}, newest first, with plain-English summaries, deadlines and the original PDF.`,
  };
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const code = params.code.toLowerCase();
  const list = await getList(isYear(code) ? "year" : "dept", code);
  if (!list) return { title: "Not found | Amar Circular", robots: { index: false } };
  const t = titles(code, list.name);
  const url = `${SITE_URL}/circulars/${code}`;
  return {
    title: t.title,
    description: t.desc,
    alternates: { canonical: url },
    robots: list.indexable ? { index: true, follow: true } : { index: false, follow: true },
    openGraph: { type: "website", url, title: t.title, description: t.desc, siteName: "Amar Circular" },
  };
}

export default async function DepartmentOrYear({ params }: Params) {
  const code = params.code.toLowerCase();
  if (code !== params.code) notFound();
  const year = isYear(code);
  const [list, hubs] = await Promise.all([getList(year ? "year" : "dept", code), getHubs()]);
  if (!list || !hubs) notFound();
  const t = titles(code, list.name);
  return (
    <div className="mx-auto max-w-[920px] py-2 sm:py-6">
      <Breadcrumbs trail={[{ name: "Home", href: "/" }, { name: "Circulars", href: "/circulars" }, { name: year ? code : code.toUpperCase() }]} />
      <h1 className="font-serif text-[30px] font-medium leading-[1.15] text-ink sm:text-[40px]">{t.h1}</h1>
      {(t.bn || list.name_bn) && (
        <p lang="bn" className="mt-1 font-bangla text-[17px] text-ink-2">
          {[t.bn, list.name_bn].filter(Boolean).join(" · ")}
        </p>
      )}
      {!year && list.name !== code.toUpperCase() && <p className="mt-2 text-[15px] font-semibold text-ink-2">Bangladesh Bank, {list.name}</p>}
      <p className="mt-3 max-w-[680px] text-[16px] leading-relaxed text-ink-2">
        {year
          ? `Bangladesh Bank issued ${list.total.toLocaleString("en")} circulars and circular letters in ${code}. `
          : `${ABOUT[code] ? `${ABOUT[code]} ` : ""}${list.total.toLocaleString("en")} ${code.toUpperCase()} circulars so far. `}
        {list.analysed.toLocaleString("en")} have a plain-English summary with deadlines and the page of the original each point
        comes from.
      </p>
      <CircularRows list={list} heading={year ? `All circulars of ${code}` : `All ${code.toUpperCase()} circulars, newest first`} />
      <HubLinks hubs={hubs} skip={`/circulars/${code}`} />
    </div>
  );
}
