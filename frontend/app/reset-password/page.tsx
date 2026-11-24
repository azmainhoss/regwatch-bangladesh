"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { confirmPasswordReset, requestPasswordReset } from "@/services/api";
import { Notice } from "@/components/ui";

/** "Forgot password?": ask for a link by email, or (opened from that link) choose a new password. */
export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token"));
  }, []);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email.trim()) return setError("Please enter your email.");
    setLoading(true);
    try {
      setDone(await requestPasswordReset(email.trim()));
    } catch (err: any) {
      setError(err?.message || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) return setError("Your password needs at least 8 characters.");
    setLoading(true);
    try {
      await confirmPasswordReset(token || "", password);
      router.replace("/dashboard");
    } catch (err: any) {
      setError(err?.message || "Something went wrong. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[440px] py-10 sm:py-16" data-free-click>
      <h1 className="font-serif text-[32px] font-medium leading-tight text-ink">{token ? "Choose a new password" : "Reset your password"}</h1>
      <p className="mt-2 text-[15px] leading-relaxed text-ink-2">
        {token ? "Enter a new password for your account. You will be signed in straight after." : "Enter the email you registered with and we will send you a link to choose a new password."}
      </p>
      <form onSubmit={token ? save : ask} className="mt-6 space-y-3 rounded-[14px] border border-line bg-surface p-5" noValidate>
        {error && <Notice kind="error">{error}</Notice>}
        {done ? (
          <Notice kind="success">{done}</Notice>
        ) : token ? (
          <div>
            <label htmlFor="rp-pw" className="field-label">
              New password
            </label>
            <div className="relative">
              <input id="rp-pw" type={show ? "text" : "password"} autoComplete="new-password" placeholder="At least 8 characters" value={password} onChange={(e) => setPassword(e.target.value)} className="field pr-10" />
              <button type="button" onClick={() => setShow((x) => !x)} aria-label={show ? "Hide password" : "Show password"} className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center text-ink-3 hover:text-ink">
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
        ) : (
          <div>
            <label htmlFor="rp-email" className="field-label">
              Email
            </label>
            <input id="rp-email" type="email" autoComplete="email" placeholder="you@bank.com" value={email} onChange={(e) => setEmail(e.target.value)} className="field" />
          </div>
        )}
        {!done && (
          <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
            {loading ? "Please wait..." : token ? "Save new password" : "Send reset link"}
          </button>
        )}
      </form>
    </div>
  );
}
