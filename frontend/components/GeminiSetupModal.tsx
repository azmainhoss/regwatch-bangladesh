"use client";

import React, { useState } from "react";
import { Check, Copy, ExternalLink } from "lucide-react";
import { Modal, ModalHeader } from "./ui";
import { Tag } from "./StatusBadge";

interface GeminiSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
  isConfigured: boolean;
  activeModel?: string;
}

const SNIPPET = `AI_PROVIDER=gemini\nGEMINI_API_KEY=PASTE_YOUR_KEY_HERE\nGEMINI_MODEL=gemini-3.8-flash`;

export default function GeminiSetupModal({ isOpen, onClose, isConfigured, activeModel = "gemini-3.8-flash" }: GeminiSetupModalProps) {
  const [copied, setCopied] = useState(false);

  const copyConfigSnippet = () => {
    navigator.clipboard.writeText(SNIPPET);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const steps: { title: string; body: React.ReactNode }[] = [
    {
      title: "Open Google AI Studio",
      body: (
        <>
          Go to{" "}
          <a href="https://aistudio.google.com/" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-accent underline">
            aistudio.google.com <ExternalLink className="h-3 w-3" />
          </a>{" "}
          and sign in with the project&apos;s Google account.
        </>
      ),
    },
    {
      title: "Create a free API key",
      body: <>Click &ldquo;Get API key&rdquo;, create a key in a new or existing project and copy it.</>,
    },
    {
      title: "Save it in backend/.env",
      body: (
        <div className="mt-2 overflow-hidden rounded-control border border-line">
          <div className="flex items-center justify-between border-b border-line bg-sunken px-3 py-1.5">
            <span className="font-mono text-xs text-ink-3">backend/.env</span>
            <button type="button" onClick={copyConfigSnippet} className="btn-ghost px-2 py-0.5 text-xs">
              {copied ? <Check className="h-3.5 w-3.5 text-ok" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="overflow-x-auto bg-surface px-3 py-2 font-mono text-[12.5px] leading-relaxed text-ink">
            {`AI_PROVIDER=gemini\nGEMINI_API_KEY=paste_your_key_here\nGEMINI_MODEL=gemini-3.8-flash`}
          </pre>
        </div>
      ),
    },
    {
      title: "Restart the backend",
      body: <>Save the file and restart the backend so it picks up the key.</>,
    },
  ];

  return (
    <Modal open={isOpen} onClose={onClose} labelledBy="gemini-title" width="max-w-xl">
      <ModalHeader id="gemini-title" title="AI setup (Gemini free tier)" subtitle="How to connect a Google AI Studio key without billing" onClose={onClose} />
      <div className="max-h-[68dvh] space-y-5 overflow-y-auto px-5 py-5 text-[14px] leading-relaxed text-ink-2">
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-panel bg-sunken px-4 py-3">
          <div>
            <p className="font-semibold text-ink">{isConfigured ? "A Gemini key is configured" : "No Gemini key configured"}</p>
            <p className="text-[13px] text-ink-3">
              Model: <span className="font-mono">{activeModel}</span>
            </p>
          </div>
          <Tag tone={isConfigured ? "ok" : "warn"}>{isConfigured ? "Ready" : "Offline engine in use"}</Tag>
        </div>

        <ul className="space-y-1.5 pl-4 [list-style:disc] marker:text-ink-3">
          <li>
            <strong className="text-ink">No billing needed.</strong> The AI Studio free tier does not ask for a card or a Cloud billing account.
          </li>
          <li>
            <strong className="text-ink">No silent paid fallback.</strong> When the free quota runs out, requests stop with a clear message.
          </li>
        </ul>

        <ol className="space-y-4">
          {steps.map((s, i) => (
            <li key={s.title} className="grid grid-cols-[1.75rem_1fr] gap-x-2">
              <span className="grid h-6 w-6 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent tabular-nums">{i + 1}</span>
              <div>
                <p className="font-semibold text-ink">{s.title}</p>
                <div className="text-[13.5px]">{s.body}</div>
              </div>
            </li>
          ))}
        </ol>

        <p className="rounded-panel border border-line px-4 py-3 text-[13px] text-ink-3">
          <strong className="text-ink-2">Privacy.</strong> RegWatch sends public Bangladesh Bank circulars to Gemini for reading. Under the free-tier terms,
          never send confidential customer data.
        </p>
      </div>
      <div className="flex justify-end border-t border-line px-5 py-3">
        <button type="button" onClick={onClose} className="btn-primary">
          Done
        </button>
      </div>
    </Modal>
  );
}
