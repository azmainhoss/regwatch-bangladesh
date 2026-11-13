import { hasBangla } from "@/components/ui";

/** The exact quote stored with an alert, with the circular and page it came from. Shown as stored, never reworded. */
export default function AlertQuote({
  text,
  reference,
  page,
  clamp = false,
}: {
  text: string;
  reference?: string | null;
  page?: number | null;
  clamp?: boolean;
}) {
  const label = reference ? `From ${reference}${page ? `, page ${page}` : ""}:` : page ? `From page ${page}:` : "Quote:";
  return (
    <div className="quote mt-2 !py-2 !text-[13.5px]">
      <p className="text-xs font-semibold text-ink-3">{label}</p>
      <p lang={hasBangla(text) ? "bn" : undefined} className={`mt-0.5 break-words ${clamp ? "line-clamp-3" : ""}`}>
        {text}
      </p>
    </div>
  );
}
