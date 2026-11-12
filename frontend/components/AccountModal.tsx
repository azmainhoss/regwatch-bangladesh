"use client";

import React, { useState } from "react";
import Link from "next/link";
import { User, Shield, LogOut, Lock, X } from "lucide-react";
import { AuthUser, loginUser, logoutUser } from "../services/api";

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  onUserChange: (user: AuthUser | null) => void;
}

export default function AccountModal({
  isOpen,
  onClose,
  currentUser,
  onUserChange,
}: AccountModalProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await loginUser(email, password);
      onUserChange(user);
      onClose();
    } catch (err: any) {
      setError(err.message || "Invalid email or password.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    logoutUser();
    onUserChange(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in">
      <div className="bg-tealNavy-900 dark:bg-tealNavy-900 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-2xl max-w-lg w-full shadow-2xl overflow-hidden transition-colors">
        {/* Header */}
        <div className="p-5 border-b border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 flex items-center justify-between bg-tealNavy-950/60 dark:bg-tealNavy-950/60 light:bg-slate-50">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-teal-100 border border-tealNavy-700 dark:border-tealNavy-700 light:border-teal-200 flex items-center justify-center text-turquoise dark:text-turquoise light:text-teal-700">
              <User className="w-5 h-5 text-turquoise" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white dark:text-white light:text-tealNavy-950">
                User Account &amp; Access
              </h3>
              <p className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-500 mt-0.5">
                RegWatch Bangladesh Authentication
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-lg text-slate-400 hover:text-white dark:hover:text-white light:hover:text-slate-900 hover:bg-tealNavy-800 dark:hover:bg-tealNavy-800 light:hover:bg-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          {currentUser ? (
            <div className="space-y-4">
              {/* Profile Card */}
              <div className="p-4 rounded-xl bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-slate-50 border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-200 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-sm font-bold text-white dark:text-white light:text-tealNavy-950 block">
                      {currentUser.full_name}
                    </span>
                    <span className="text-xs text-slate-400 dark:text-slate-400 light:text-slate-600 block mt-0.5 font-mono">
                      {currentUser.email}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 dark:bg-emerald-950 light:bg-emerald-100 text-emerald-300 dark:text-emerald-300 light:text-emerald-800 border border-emerald-700/80 font-bold">
                    Active Session
                  </span>
                </div>

                <div className="pt-3 border-t border-tealNavy-800 dark:border-tealNavy-800 light:border-slate-200 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 block uppercase font-medium">
                      Role
                    </span>
                    <span className="text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-semibold mt-0.5 block">
                      {currentUser.is_superuser ? "Platform administrator" : "Standard user"}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 dark:text-slate-400 light:text-slate-500 block uppercase font-medium">
                      Phone
                    </span>
                    <span className="text-slate-200 dark:text-slate-200 light:text-tealNavy-950 font-semibold mt-0.5 block">
                      {currentUser.phone_number || "-"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Security info */}
              <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-400 light:text-slate-600">
                <Shield className="w-4 h-4 text-turquoise" />
                <span>Encrypted session with role-based document access.</span>
              </div>

              {/* Action buttons */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={handleLogout}
                  className="px-3.5 py-2 text-xs text-rose-300 hover:text-rose-200 bg-rose-950/40 hover:bg-rose-950/80 border border-rose-800/60 rounded-lg transition flex items-center gap-1.5"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Sign Out</span>
                </button>
                {currentUser.is_superuser ? (
                  <Link
                    href="/admin"
                    onClick={onClose}
                    className="text-xs text-turquoise hover:text-turquoise-bright font-semibold font-mono underline"
                  >
                    Open Admin Console &rarr;
                  </Link>
                ) : (
                  <span className="text-[11px] text-slate-400 font-mono">Institutional Session Active</span>
                )}
              </div>
            </div>
          ) : (
            <form onSubmit={handleLogin} className="space-y-4">
              {error && (
                <div className="p-3 text-xs bg-rose-950/60 border border-rose-800 rounded-lg text-rose-300">
                  {error}
                </div>
              )}
              <div>
                <label className="text-xs font-semibold text-slate-300 dark:text-slate-300 light:text-slate-700 block mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 dark:text-slate-300 light:text-slate-700 block mb-1">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  className="w-full bg-tealNavy-950 dark:bg-tealNavy-950 light:bg-white border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 rounded-xl px-3.5 py-2 text-xs text-slate-200 dark:text-slate-200 light:text-tealNavy-950 focus:outline-none focus:border-turquoise"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 bg-turquoise hover:bg-turquoise-bright text-tealNavy-950 text-xs font-bold rounded-xl transition shadow-sm disabled:opacity-50"
              >
                {loading ? "Verifying..." : "Sign In to RegWatch"}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
