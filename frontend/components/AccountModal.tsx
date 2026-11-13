"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ArrowRight, LogOut } from "lucide-react";
import { AuthUser, loginUser, logoutUser, registerUser } from "../services/api";
import { Modal, ModalHeader, Notice } from "./ui";

const MIN_PASSWORD = 8;

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  onUserChange: (user: AuthUser | null) => void;
}

export default function AccountModal({ isOpen, onClose, currentUser, onUserChange }: AccountModalProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [fullName, setFullName] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const switchMode = (next: "signin" | "signup") => {
    setMode(next);
    setError(null);
    setPassword("");
    setConfirm("");
  };

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const name = fullName.trim();
    if (!name) return setError("Please enter your full name.");
    if (password.length < MIN_PASSWORD) return setError(`Your password needs at least ${MIN_PASSWORD} characters.`);
    if (password !== confirm) return setError("The two passwords do not match.");
    setLoading(true);
    try {
      // registerUser saves the session and tells every screen, so the header shows the name at once.
      const user = await registerUser({ email: email.trim(), password, full_name: name });
      onUserChange(user);
      setPassword("");
      setConfirm("");
      setFullName("");
      setMode("signin");
      onClose();
    } catch (err: any) {
      const msg: string = err?.message || "";
      setError(/valid email/i.test(msg) ? "That email address does not look right." : msg || "Could not create the account.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await loginUser(email.trim(), password);
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
    setEmail("");
    setMode("signin");
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
            title={mode === "signin" ? "Sign in" : "Create an account"}
            subtitle={
              mode === "signin"
                ? "Sign in to your RegWatch account."
                : "It takes a few seconds. You will be signed in at once."
            }
            onClose={onClose}
          />
          <form onSubmit={mode === "signin" ? handleLogin : handleSignup} className="space-y-4 px-5 py-5">
            {error && <Notice kind="error">{error}</Notice>}
            {mode === "signup" && (
              <div>
                <label htmlFor="signup-name" className="field-label">
                  Full name
                </label>
                <input
                  id="signup-name"
                  type="text"
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  disabled={loading}
                  className="field"
                />
              </div>
            )}
            <div>
              <label htmlFor="login-email" className="field-label">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                autoComplete={mode === "signin" ? "username" : "email"}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={loading}
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
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={mode === "signup" ? MIN_PASSWORD : undefined}
                disabled={loading}
                className="field"
              />
              {mode === "signup" && <p className="mt-1 text-[12.5px] text-ink-3">At least {MIN_PASSWORD} characters.</p>}
            </div>
            {mode === "signup" && (
              <div>
                <label htmlFor="signup-confirm" className="field-label">
                  Confirm password
                </label>
                <input
                  id="signup-confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  required
                  disabled={loading}
                  className="field"
                />
              </div>
            )}
            <button type="submit" disabled={loading} className="btn-primary w-full py-2.5 text-[14px]">
              {mode === "signin" ? (loading ? "Signing in..." : "Sign in") : loading ? "Creating account..." : "Create account"}
            </button>
            <p className="text-center text-[13.5px] text-ink-3">
              {mode === "signin" ? "New here?" : "Already have an account?"}{" "}
              <button
                type="button"
                onClick={() => switchMode(mode === "signin" ? "signup" : "signin")}
                disabled={loading}
                className="font-semibold text-accent hover:underline disabled:opacity-60"
              >
                {mode === "signin" ? "Create an account" : "Sign in"}
              </button>
            </p>
          </form>
        </>
      )}
    </Modal>
  );
}
