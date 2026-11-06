"use client";

import React, { useState } from "react";
import { Sparkles, X, ShieldAlert, CheckCircle2, Copy, Check, ExternalLink, Terminal, AlertCircle } from "lucide-react";

interface GeminiSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
  isConfigured: boolean;
  activeModel?: string;
}

export default function GeminiSetupModal({
  isOpen,
  onClose,
  isConfigured,
  activeModel = "gemini-3.8-flash",
}: GeminiSetupModalProps) {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const copyConfigSnippet = () => {
    const snippet = `AI_PROVIDER=gemini\nGEMINI_API_KEY=PASTE_YOUR_KEY_HERE\nGEMINI_MODEL=gemini-3.8-flash`;
    navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in">
      <div className="bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-2xl max-w-2xl w-full shadow-2xl overflow-hidden transition-colors">
        {/* Header */}
        <div className="p-6 border-b border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 flex items-center justify-between bg-tealNavy-950/60 dark:bg-tealNavy-950/60 light:bg-teal-50/50">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200 flex items-center justify-center text-turquoise dark:text-turquoise light:text-teal-700">
              <Sparkles className="w-5 h-5 text-turquoise" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white dark:text-white light:text-tealNavy-950 flex items-center gap-2">
                Google Gemini Free-Tier Configuration
                <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-turquoise-dark/50 text-turquoise border border-turquoise/40">
                  ZERO-COST POLICY
                </span>
              </h3>
              <p className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 mt-0.5">
                Non-Technical Owner Setup Guide - Personal Google AI Studio Account
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white dark:hover:text-white light:hover:text-slate-900 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto text-xs text-slate-300 dark:text-slate-300 light:text-slate-700">
          {/* Status Badge */}
          <div className="flex items-center justify-between p-3.5 rounded-xl bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200">
            <div className="flex items-center space-x-2.5">
              {isConfigured ? (
                <CheckCircle2 className="w-4 h-4 text-semantic-success" />
              ) : (
                <AlertCircle className="w-4 h-4 text-semantic-warning" />
              )}
              <div>
                <span className="font-semibold block text-white dark:text-white light:text-tealNavy-950">
                  {isConfigured ? "Gemini Key Configured" : "Operating in Offline Sandbox Mode"}
                </span>
                <span className="text-[11px] text-slate-400 dark:text-slate-400 light:text-slate-500 font-mono">
                  Active Model: {activeModel}
                </span>
              </div>
            </div>
            <span className="text-[10px] font-mono px-2 py-1 rounded bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 font-bold">
              {isConfigured ? "READY FOR INGESTION" : "MOCK ENGINE ACTIVE"}
            </span>
          </div>

          {/* Zero Cost Policy Guarantee */}
          <div className="p-4 rounded-xl bg-tealNavy-950/80 dark:bg-tealNavy-950/80 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2">
            <h4 className="font-bold text-white dark:text-white light:text-tealNavy-950 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-turquoise" />
              Strict Zero-Cost Financial Policy
            </h4>
            <ul className="space-y-1.5 text-slate-400 dark:text-slate-400 light:text-slate-600 list-disc pl-5 leading-relaxed">
              <li>
                <strong className="text-slate-200 dark:text-slate-200 light:text-slate-900">No Billing Required:</strong> Google AI Studio free tier does not require enabling Google Cloud billing or adding credit cards.
              </li>
              <li>
                <strong className="text-slate-200 dark:text-slate-200 light:text-slate-900">No Silent Paid Fallback:</strong> If free-tier rate limits or quota are exhausted, requests halt immediately with an informative message.
              </li>
              <li>
                <strong className="text-slate-200 dark:text-slate-200 light:text-slate-900">Supported Free Model:</strong> Configured for <code className="text-turquoise font-mono">gemini-3.8-flash</code>.
              </li>
            </ul>
          </div>

          {/* Step by step owner setup */}
          <div className="space-y-3">
            <h4 className="font-bold text-white dark:text-white light:text-tealNavy-950">
              Simple 4-Step Setup for Project Owner:
            </h4>

            <div className="space-y-2">
              <div className="p-3 rounded-lg bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-1">
                <span className="font-semibold text-turquoise dark:text-turquoise light:text-teal-700 block">
                  Step 1: Open Google AI Studio
                </span>
                <p className="text-slate-400 dark:text-slate-400 light:text-slate-600">
                  Go to <a href="https://aistudio.google.com/" target="_blank" rel="noreferrer" className="text-turquoise underline font-semibold inline-flex items-center gap-1">aistudio.google.com <ExternalLink className="w-3 h-3" /></a> and sign in with your personal Google account.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-1">
                <span className="font-semibold text-turquoise dark:text-turquoise light:text-teal-700 block">
                  Step 2: Generate Free API Key
                </span>
                <p className="text-slate-400 dark:text-slate-400 light:text-slate-600">
                  Click <strong>"Get API key"</strong> in the top left, create a key in a new or existing project, and copy it to your clipboard.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-turquoise dark:text-turquoise light:text-teal-700">
                    Step 3: Save to backend/.env
                  </span>
                  <button
                    onClick={copyConfigSnippet}
                    className="text-[11px] text-slate-300 hover:text-white flex items-center gap-1 font-mono bg-tealNavy-800 dark:bg-tealNavy-800 light:bg-white px-2 py-1 rounded border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 transition"
                  >
                    {copied ? <Check className="w-3 h-3 text-semantic-success" /> : <Copy className="w-3 h-3" />}
                    <span>{copied ? "Copied" : "Copy Template"}</span>
                  </button>
                </div>
                <div className="p-2.5 rounded bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-900 font-mono text-[11px] text-slate-300 border border-tealNavy-800 space-y-0.5">
                  <div className="text-slate-500"># backend/.env</div>
                  <div>AI_PROVIDER=gemini</div>
                  <div>GEMINI_API_KEY=paste_your_key_here</div>
                  <div>GEMINI_MODEL=gemini-3.8-flash</div>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-1">
                <span className="font-semibold text-turquoise dark:text-turquoise light:text-teal-700 block">
                  Step 4: Restart Backend
                </span>
                <p className="text-slate-400 dark:text-slate-400 light:text-slate-600">
                  Save the file and restart the backend. The application will immediately recognize your key with zero cost.
                </p>
              </div>
            </div>
          </div>

          {/* Free Tier Data Privacy Notice */}
          <div className="p-3 rounded-lg bg-tealNavy-950/60 dark:bg-tealNavy-950/60 light:bg-slate-100 border border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 text-[11px] text-slate-400 dark:text-slate-400 light:text-slate-600 leading-relaxed">
            <strong className="text-slate-300 dark:text-slate-300 light:text-slate-800">Free Tier Privacy Notice:</strong> RegWatch sends public Bangladesh Bank regulatory circulars to Google Gemini for extraction. In accordance with Google AI Studio Free Tier terms, never submit non-public or confidential bank customer data.
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 flex justify-end bg-tealNavy-950/40 dark:bg-tealNavy-950/40 light:bg-slate-50">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-turquoise hover:bg-turquoise-bright text-tealNavy-950 font-bold text-xs transition shadow-sm"
          >
            Understood
          </button>
        </div>
      </div>
    </div>
  );
}
