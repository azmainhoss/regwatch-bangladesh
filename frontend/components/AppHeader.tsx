"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ShieldCheck, AlertTriangle, Cpu, Sparkles, Terminal } from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import { fetchProviderStatus, ProviderStatusInfo } from "../services/api";

export default function AppHeader() {
  const pathname = usePathname();
  const [providerInfo, setProviderInfo] = useState<ProviderStatusInfo | null>(null);

  useEffect(() => {
    fetchProviderStatus()
      .then((info) => setProviderInfo(info))
      .catch(() => {
        // Fallback info if API error
        setProviderInfo({
          configured_provider: "mock",
          default_model: "mock-regulatory-v1",
          gemini_api_key_configured: false,
          status: "MOCK_SANDBOX",
          timeout_seconds: 60,
          max_retries: 3,
          billing_policy: "ZERO_COST_FREE_TIER",
        });
      });
  }, []);

  const isGeminiLive = providerInfo?.configured_provider === "gemini" && providerInfo?.gemini_api_key_configured;

  return (
    <header className="border-b border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 bg-tealNavy-900/95 dark:bg-tealNavy-900/95 light:bg-white/95 backdrop-blur sticky top-0 z-50 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand identity */}
        <div className="flex items-center space-x-6">
          <Link href="/" className="flex items-center space-x-3 group">
            <div className="w-9 h-9 rounded-lg bg-tealNavy-800 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 flex items-center justify-center text-turquoise group-hover:border-turquoise group-hover:shadow-[0_0_12px_rgba(45,212,191,0.3)] transition">
              <ShieldCheck className="w-5 h-5 text-turquoise" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 font-semibold text-lg tracking-tight text-white dark:text-white light:text-tealNavy-950">
                <span>RegWatch</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-tealNavy-800 dark:bg-tealNavy-800 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 font-mono border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200 font-bold">
                  BD
                </span>
              </div>
              <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 block tracking-wider uppercase font-medium">
                Bangladesh Regulatory Intelligence
              </span>
            </div>
          </Link>

          {/* Navigation */}
          <nav className="hidden md:flex items-center space-x-1 pl-4 border-l border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 text-sm font-medium">
            <Link
              href="/"
              className={`px-3 py-1.5 rounded-md transition ${
                pathname === "/"
                  ? "bg-tealNavy-800 dark:bg-tealNavy-800 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 font-semibold border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200"
                  : "text-slate-300 dark:text-slate-300 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-850 dark:hover:bg-tealNavy-850 light:hover:bg-slate-100"
              }`}
            >
              Professional Feed
            </Link>
            <Link
              href="/admin"
              className={`px-3 py-1.5 rounded-md transition ${
                pathname === "/admin"
                  ? "bg-tealNavy-800 dark:bg-tealNavy-800 light:bg-teal-50 text-turquoise dark:text-turquoise light:text-teal-700 font-semibold border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200"
                  : "text-slate-300 dark:text-slate-300 light:text-slate-600 hover:text-white dark:hover:text-white light:hover:text-tealNavy-950 hover:bg-tealNavy-850 dark:hover:bg-tealNavy-850 light:hover:bg-slate-100"
              }`}
            >
              Admin Console & Ingestion
            </Link>
          </nav>
        </div>

        {/* Telemetry and Controls */}
        <div className="flex items-center space-x-3">
          {/* AI Provider Telemetry Pill */}
          <div
            className={`hidden lg:flex items-center space-x-2 text-xs rounded-full px-3 py-1 border transition ${
              isGeminiLive
                ? "bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-50 border-turquoise/40 text-turquoise"
                : "bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 text-slate-300 dark:text-slate-300 light:text-slate-700"
            }`}
            title={
              isGeminiLive
                ? `Active: Google Gemini (${providerInfo?.default_model}) - Zero-Cost Free Tier Policy Active`
                : "Active: Mock Regulatory Rule Engine (Air-Gapped Sandbox)"
            }
          >
            {isGeminiLive ? (
              <Sparkles className="w-3.5 h-3.5 text-turquoise animate-pulse" />
            ) : (
              <Cpu className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span className="font-mono text-[11px]">
              {isGeminiLive ? `Gemini: ${providerInfo?.default_model} (Zero-Cost)` : "AI: Mock Engine (Sandbox)"}
            </span>
          </div>

          {/* BB Portal WAF Indicator */}
          <div
            className="hidden sm:flex items-center space-x-2 text-xs bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-amber-50 border border-amber-500/40 rounded-full px-3 py-1 cursor-default"
            title="Automated portal crawler restricted by Bangladesh Bank Imperva Incapsula WAF. Operating mode: Manual Ingestion Dropzone Active."
          >
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-amber-300 dark:text-amber-300 light:text-amber-800 font-mono text-[11px]">
              BB Portal: WAF Restricted (Manual Deposit Active)
            </span>
          </div>

          {/* Theme Toggle */}
          <ThemeToggle />

          {/* System version */}
          <div className="hidden sm:flex items-center space-x-1.5 text-xs font-mono text-slate-400 dark:text-slate-400 light:text-slate-600 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded px-2.5 py-1 bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100">
            <Terminal className="w-3 h-3 text-turquoise" />
            <span>v1.0.0-PROD</span>
          </div>
        </div>
      </div>
    </header>
  );
}
