"use client";

import React, { useState } from "react";
import { AuthUser, loginUser, registerUser } from "../services/api";
import { Notice } from "./ui";

const MIN_PASSWORD = 8;

export type AuthMode = "signin" | "signup";

/** Email and password form for signing in or creating an account. Shared by the sign-in screen and the account dialog. */
export default function AuthForm({
  mode,
  onModeChange,
  onDone,
  hideSwitch = false,
}: {
  mode: AuthMode;
  onModeChange: (m: AuthMode) => void;
  onDone: (user: AuthUser) => void;
  /** Hide the "New here? / Already have an account?" switch (admin login). */
  hideSwitch?: boolean;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const switchMode = (next: AuthMode) => {
    onModeChange(next);
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
      // registerUser saves the session and tells every screen.
      const user = await registerUser({ email: email.trim(), password, full_name: name });
      setPassword("");
      setConfirm("");
      setFullName("");
      setLoading(false);
      onDone(user);
    } catch (err: any) {
      const msg: string = err?.message || "";
      setError(/valid email/i.test(msg) ? "That email address does not look right." : msg || "Could not create the account.");
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await loginUser(email.trim(), password);
      setPassword("");
      setLoading(false);
      onDone(user);
    } catch (err: any) {
      setError(err.message || "Invalid email or password.");
      setLoading(false);
    }
  };

  return (
    <form onSubmit={mode === "signin" ? handleLogin : handleSignup} className="space-y-4">
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
      {!hideSwitch && (
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
      )}
    </form>
  );
}
