import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SITE_URL } from "@/services/serverApi";
import { getHubs, getList } from "@/services/publicApi";
import { Breadcrumbs, CircularRows, HubLinks } from "@/components/seo/CircularHub";

export const revalidate = 600;

/** A line on each subject in the words people search with (unique text for each subject page). */
const ABOUT: Record<string, { lead: string; bn?: string }> = {
  ecl: { lead: "Expected credit loss (ECL) under IFRS 9: how banks stage loans and provide for expected losses." },
  provision: {
    lead: "Loan classification (SMA, SS, DF, BL) and provisioning rules, including the BRPD master circulars on classification and provisioning.",
    bn: "ঋণ শ্রেণীকরণ ও প্রভিশনিং সার্কুলার",
  },
  "default-loans": {
    lead: "Loan rescheduling, restructuring, write-off and exit policies for defaulted loans.",
    bn: "ঋণ পুনঃতফসিল, অবলোপন ও খেলাপি ঋণ সার্কুলার",
  },
  capital: { lead: "Capital adequacy under Basel III: CRAR, capital buffers, leverage ratio, ICAAP and SRP." },
  liquidity: { lead: "CRR, SLR, LCR, NSFR and the advance-deposit ratio (ADR), and liquidity support for banks.", bn: "তারল্য, সিআরআর ও এসএলআর" },
  "interest-rate": { lead: "Lending and deposit interest rates, SMART rate, spreads and rate caps.", bn: "সুদহার সার্কুলার" },
  credit: { lead: "Credit policy and credit risk: large loans, single borrower exposure limits, collateral and loan approval." },
  "sme-agri": {
    lead: "CMSME (SME) finance, agricultural and rural credit, and the refinance and stimulus schemes for them.",
    bn: "এসএমই ও কৃষি ঋণ সার্কুলার",
  },
  green: { lead: "Green banking and sustainable finance: climate risk, ESG and environmental risk management." },
  forex: {
    lead: "Foreign exchange: FX accounts, exchange rates, inward and outward remittance, remittance incentives and exchange houses.",
    bn: "বৈদেশিক মুদ্রা ও রেমিট্যান্স সার্কুলার",
  },
  trade: { lead: "Import and export: LCs and LC margins, export retention quota (ERQ), EDF, cash incentives and deferred payments.", bn: "আমদানি ও রপ্তানি সার্কুলার" },
  aml: { lead: "Anti-money laundering and counter terrorist financing (AML/CFT): KYC, CDD, STR and CTR reporting, mostly from BFIU.", bn: "মানিলন্ডারিং প্রতিরোধ সার্কুলার" },
  payments: { lead: "Payment systems and digital banking: MFS, RTGS, BEFTN, NPSB, QR payments, digital banks and e-wallets." },
  cards: { lead: "Credit, debit and prepaid cards: card limits, card charges and the latest card rules." },
  ict: { lead: "ICT and cyber security: the ICT security guideline, IT risk, data protection and cloud use by banks." },
  governance: { lead: "Bank governance: boards of directors, MD/CEO appointments and the Bank Company Act rules." },
  "internal-audit": { lead: "Internal control and compliance (ICC), internal audit and audit committees." },
  "financial-statements": { lead: "Financial statements, external audit, disclosures and dividend declaration by banks." },
  reporting: { lead: "Returns and reports banks submit to Bangladesh Bank, with formats and deadlines." },
  risk: { lead: "Risk management and stress testing: core risk guidelines, risk appetite, market and operational risk." },
  branches: { lead: "Branches, sub-branches, agent banking outlets, booths and ATMs." },
  customer: { lead: "Customer protection, complaint handling and financial inclusion." },
  deposits: { lead: "Deposit products, savings schemes, account opening rules, dormant and unclaimed accounts." },
  charges: { lead: "Bank service charges, fees, the schedule of charges and waivers." },
  islamic: { lead: "Islamic (Shariah-based) banking: Islamic windows, mudaraba, sukuk and the rules for Islamic banks." },
  treasury: { lead: "Treasury and money market: call money, repo, treasury bills and bonds, and banks' capital market investment." },
  currency: { lead: "Currency notes and coins: new notes, soiled notes, coins and cash handling.", bn: "নোট ও মুদ্রা সার্কুলার" },
  nbfi: { lead: "NBFIs (finance companies): the rules from DFIM for non-bank financial institutions." },
  hr: { lead: "Bank staff: salaries, recruitment, training, incentive bonuses and code of conduct." },
  operations: { lead: "Banking hours, bank holidays (Eid and other closures) and office timing.", bn: "ব্যাংক লেনদেনের সময় ও ছুটির নোটিশ" },
};

type Params = { params: { code: string } };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const list = await getList("topic", params.code);
  if (!list) return { title: "Not found | Amar Circular", robots: { index: false } };
  const title = `${list.name}: Bangladesh Bank circulars | Amar Circular`;
  const desc = `${ABOUT[params.code]?.lead || list.name} Every Bangladesh Bank circular on it, newest first, with summaries and the original PDF.`;
  const url = `${SITE_URL}/circulars/topic/${params.code}`;
  return {
    title,
    description: desc.length > 160 ? `${desc.slice(0, 157).trimEnd()}…` : desc,
    alternates: { canonical: url },
    robots: list.indexable ? { index: true, follow: true } : { index: false, follow: true },
    openGraph: { type: "website", url, title, description: desc, siteName: "Amar Circular" },
  };
}

export default async function TopicPage({ params }: Params) {
  const [list, hubs] = await Promise.all([getList("topic", params.code), getHubs()]);
  if (!list || !hubs) notFound();
  const about = ABOUT[params.code];
  return (
    <div className="mx-auto max-w-[920px] py-2 sm:py-6">
      <Breadcrumbs trail={[{ name: "Home", href: "/" }, { name: "Circulars", href: "/circulars" }, { name: list.name }]} />
      <h1 className="font-serif text-[30px] font-medium leading-[1.15] text-ink sm:text-[40px]">{list.name} circulars</h1>
      {about?.bn && (
        <p lang="bn" className="mt-1 font-bangla text-[17px] text-ink-2">
          {about.bn}
        </p>
      )}
      <p className="mt-3 max-w-[680px] text-[16px] leading-relaxed text-ink-2">
        {about ? `${about.lead} ` : ""}
        Bangladesh Bank has issued {list.total.toLocaleString("en")} circulars on this; {list.analysed.toLocaleString("en")} have a
        plain-English summary with deadlines and the page of the original each point comes from.
      </p>
      <CircularRows list={list} heading="All circulars on this subject, newest first" />
      <HubLinks hubs={hubs} skip={`/circulars/topic/${params.code}`} />
    </div>
  );
}
