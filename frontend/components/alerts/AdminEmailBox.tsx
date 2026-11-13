"use client";

import { useEffect, useState } from "react";
import { Tag, type Tone } from "@/components/StatusBadge";
import { Notice, SkeletonLine } from "@/components/ui";
import { loadEmailAdmin, retryEmail, sendTestEmail, useAlerts } from "@/services/alertsStore";
import { fullWhen } from "./AlertRow";

const KIND: Record<string, string> = { INSTANT: "Right away", DIGEST: "Daily summary", TEST: "Test" };
const STATUS: Record<string, { label: string; tone: Tone }> = {
  SENT: { label: "Sent", tone: "ok" },
  PENDING: { label: "Waiting", tone: "info" },
  SENDING: { label: "Sending", tone: "info" },
  FAILED: { label: "Failed", tone: "bad" },
  EXPIRED: { label: "Expired", tone: "muted" },
};
const TLS: Record<string, string> = { starttls: "STARTTLS", ssl: "SSL", none: "None" };

function Line({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3 border-b border-line py-2 text-[14px] last:border-b-0">
      <dt className="text-ink-3">{label}</dt>
      <dd className="min-w-0 break-words text-right font-semibold text-ink">{value}</dd>
    </div>
  );
}
const yes = (b: boolean) => (b ? "Yes" : "No");

/** Platform staff only: whether the server can send email, and a way to try it. */
export default function AdminEmailBox() {
  const s = useAlerts();
  const st = s.emailStatus;
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    void loadEmailAdmin(true);
    const t = setInterval(() => {
      if (!document.hidden) void loadEmailAdmin(true);
    }, 10000);
    return () => clearInterval(t);
  }, []);

  const configured = st?.configured ?? s.emailConfigured;
  const test = async () => {
    if (sending) return;
    setSending(true);
    setResult(null);
    setResult(await sendTestEmail());
    setSending(false);
  };

  return (
    <section className="panel space-y-4 p-4 sm:p-5" aria-labelledby="email-server-title" data-testid="admin-email-box">
      <h2 id="email-server-title" className="text-[16px] font-semibold text-ink">
        Email server
      </h2>
      {!st ? (
        <div className="space-y-2" aria-busy="true">
          <SkeletonLine className="h-4 w-1/2" />
          <SkeletonLine className="h-4 w-2/3" />
        </div>
      ) : (
        <>
          <dl>
            <Line label="Set up" value={yes(st.configured)} />
            <Line label="Server" value={st.host ? `${st.host}${st.port ? `:${st.port}` : ""}` : "Not set"} />
            <Line label="Connection security" value={TLS[st.tls_mode] ?? st.tls_mode} />
            <Line label="Sends from" value={st.from_address || "Not set"} />
            <Line label="User name set" value={yes(st.username_set)} />
            <Line label="Password set" value={yes(st.password_set)} />
            <Line label="Background sending running" value={yes(st.worker_running)} />
            <Line
              label="Emails"
              value={`${st.outbox.sent_24h} sent in 24 h, ${st.outbox.pending + st.outbox.sending} waiting, ${st.outbox.failed} failed, ${st.outbox.expired} expired`}
            />
          </dl>
          {st.last_error && <Notice kind="warning">Last problem: {st.last_error}</Notice>}
        </>
      )}

      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn-secondary min-h-[44px] sm:min-h-0"
            disabled={!configured || sending}
            title={configured ? undefined : "Email is not set up on this server."}
            onClick={() => void test()}
          >
            {sending && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-3 border-t-transparent" aria-hidden />}
            Send me a test email
          </button>
          {!configured && <span className="text-[13px] text-ink-3">Email is not set up on this server.</span>}
        </div>
        {result && <Notice kind={result.ok ? "success" : "error"}>{result.text}</Notice>}
      </div>

      <div>
        <h3 className="text-[14px] font-semibold text-ink">Recent emails</h3>
        {!s.outbox ? (
          <SkeletonLine className="mt-2 h-4 w-1/2" />
        ) : s.outbox.length === 0 ? (
          <p className="mt-1 text-[13.5px] text-ink-3">No emails yet.</p>
        ) : (
          <>
            <table className="mt-2 hidden w-full text-left text-[13.5px] sm:table">
              <thead className="text-ink-3">
                <tr className="border-b border-line">
                  <th className="py-1.5 pr-2 font-semibold">Kind</th>
                  <th className="py-1.5 pr-2 font-semibold">Status</th>
                  <th className="py-1.5 pr-2 font-semibold">Tries</th>
                  <th className="py-1.5 pr-2 font-semibold">To</th>
                  <th className="py-1.5 pr-2 font-semibold">Problem</th>
                  <th className="py-1.5 pr-2 font-semibold">Time</th>
                  <th className="py-1.5" />
                </tr>
              </thead>
              <tbody>
                {s.outbox.map((r) => {
                  const spec = STATUS[r.status] ?? { label: r.status, tone: "muted" as Tone };
                  return (
                    <tr key={r.id} className="border-b border-line align-top last:border-b-0">
                      <td className="py-2 pr-2">{KIND[r.kind] ?? r.kind}</td>
                      <td className="py-2 pr-2">
                        <Tag tone={spec.tone}>{spec.label}</Tag>
                      </td>
                      <td className="py-2 pr-2 tabular-nums">{r.attempts}</td>
                      <td className="py-2 pr-2 break-all">{r.to_masked}</td>
                      <td className="max-w-[220px] break-words py-2 pr-2 text-ink-2">{r.last_error || ""}</td>
                      <td className="whitespace-nowrap py-2 pr-2 text-ink-3">{fullWhen(r.sent_at || r.created_at)}</td>
                      <td className="py-2 text-right">
                        {(r.status === "FAILED" || r.status === "EXPIRED") && (
                          <button type="button" className="btn-secondary" onClick={() => void retryEmail(r.id)}>
                            Retry
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <ul className="mt-2 space-y-2 sm:hidden">
              {s.outbox.map((r) => {
                const spec = STATUS[r.status] ?? { label: r.status, tone: "muted" as Tone };
                return (
                  <li key={r.id} className="rounded-panel border border-line p-3 text-[13.5px]">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-ink">{KIND[r.kind] ?? r.kind}</span>
                      <Tag tone={spec.tone}>{spec.label}</Tag>
                      <span className="meta">{r.attempts} tries</span>
                    </div>
                    <p className="mt-1 break-all text-ink-2">{r.to_masked}</p>
                    {r.last_error && <p className="mt-1 break-words text-ink-2">{r.last_error}</p>}
                    <p className="meta mt-1">{fullWhen(r.sent_at || r.created_at)}</p>
                    {(r.status === "FAILED" || r.status === "EXPIRED") && (
                      <button type="button" className="btn-secondary mt-2 min-h-[44px]" onClick={() => void retryEmail(r.id)}>
                        Retry
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
