import { SITE_URL } from "@/services/serverApi";
import { getHubs, getList, refLabel } from "@/services/publicApi";

export const revalidate = 3600;

/** llms.txt: a plain map of the site for AI assistants and AI search (https://llmstxt.org). */
export async function GET() {
  const [hubs, latest] = await Promise.all([getHubs().catch(() => null), getList("latest", "all").catch(() => null)]);
  const lines = [
    "# Amar Circular",
    "",
    "> Bangladesh Bank circulars, summarised the day they are issued: what changed, what banks must do, deadlines, and the page of the original PDF each point comes from. Covers every department (BRPD, FEPD, DOS, BFIU, PSD, DFIM, SFD and more). Not an official source: always check the original circular on bb.org.bd.",
    "",
    "## Lists",
    `- [Latest Bangladesh Bank circulars](${SITE_URL}/circulars): every circular, newest first`,
    ...(hubs?.departments ?? []).map((d) => `- [${d.code.toUpperCase()} circulars](${SITE_URL}/circulars/${d.code}): ${d.name}, ${d.total} circulars`),
    ...(hubs?.years ?? []).map((y) => `- [Circulars of ${y.code}](${SITE_URL}/circulars/${y.code})`),
    "",
    "## Subjects",
    ...(hubs?.topics ?? []).map((t) => `- [${t.name}](${SITE_URL}/circulars/topic/${t.code})`),
    "",
    "## Newest summarised circulars",
    ...(latest?.items ?? [])
      .filter((i) => i.analysed)
      .slice(0, 40)
      .map((i) => `- [${refLabel(i.reference_number, i.publication_date) || i.department}: ${i.title}](${SITE_URL}${i.path})`),
    "",
  ];
  return new Response(lines.join("\n"), { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
