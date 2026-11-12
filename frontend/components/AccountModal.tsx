"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ArrowRight, LogOut } from "lucide-react";
import { AuthUser, loginUser, logoutUser } from "../services/api";
import { Modal, ModalHeader, Notice } from "./ui";

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  onUserChange: (user: AuthUser | null) => void;
}

export default function AccountModal({ isOpen, onClose, currentUser, onUserChange }: AccountModalProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await loginUser(email, password);
      onUserChange(user);
      setPassword("");
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
    <Modal open={isOpen} onClose={onClose} labelledBy="account-title" width="max-w-md">
      {currentUser ? (
        <>
          <ModalHeader id="account-title" title="Your account" onClose={onClose} />
          <div className="space-y-5 px-5 py-5">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent-soft text-[15px] font-bold text-accent">
                {currentUser.full_name
                  .split(/\s+/)
                  .map((p) => p[0])
                  .slice(0, 2)
                  .join("")
                  .toUpperCase()}
              </span>
              <div className="min-w-0">
                <p className="truncate text-[16px] font-semibold text-ink">{currentUser.full_name}</p>
                <p className="truncate text-[13.5px] text-ink-3">{currentUser.email}</p>
              </div>
            </div>

            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-y border-line py-4 text-[14px]">
              <div>
                <dt className="text-[12.5px] text-ink-3">Role</dt>
                <dd className="mt-0.5 font-semibold text-ink">{currentUser.is_superuser ? "Administrator" : "Standard user"}</dd>
              </div>
              <div>
                <dt className="text-[12.5px] text-ink-3">Phone</dt>
                <dd className="mt-0.5 font-semibold text-ink tabular-nums">{currentUser.phone_number || "Not set"}</dd>
              </div>
            </dl>

            <div className="flex items-center justify-between gap-3">
              <button type="button" onClick={handleLogout} className="btn-danger">
                <LogOut className="h-4 w-4" strokeWidth={1.75} />
                Sign out
              </button>
              {currentUser.is_superuser && (
                <Link href="/admin" onClick={onClose} className="btn-secondary">
                  Admin console
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} />
                </Link>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
          <ModalHeader
            id="account-title"
            title="Sign in"
            subtitle="Use the account your compliance team set up for you."
            onClose={onClose}
          />
          <form onSubmit={handleLogin} className="space-y-4 px-5 py-5">
            {error && <Notice kind="error">{error}</Notice>}
            <div>
              <label htmlFor="login-email" className="field-label">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="field"
              />
            </div>
            <div>
              <label htmlFor="login-password" className="field-label">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="field"
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5 text-[14px]">
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </>
      )}
    </Modal>
  );
}
