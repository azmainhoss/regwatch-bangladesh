"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import AuthForm from "../../../components/AuthForm";
import { Notice } from "../../../components/ui";
import { getStoredUser, logoutUser, type AuthUser } from "../../../services/api";

/** Admin login: email and password. Only administrator accounts get through; anyone else is signed out again. */
export default function AdminLoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (getStoredUser()?.is_superuser) router.replace("/admin");
  }, [router]);

  const done = (u: AuthUser) => {
    if (u.is_superuser) {
      router.replace("/admin");
      return;
    }
    logoutUser();
    setError("This account is not an administrator.");
  };

  return (
    // data-free-click: this page works for visitors (the site-wide Register now prompt stays out of the way).
    <div data-free-click className="mx-auto my-10 w-full max-w-[400px]">
      <div className="panel px-6 py-7 shadow-panel">
        <ShieldCheck className="h-6 w-6 text-accent" strokeWidth={1.75} />
        <h1 className="mt-3 text-[20px] font-semibold text-ink">Admin login</h1>
        <p className="mb-5 mt-1 text-[14px] text-ink-3">For Amar Circular administrators.</p>
        {error && (
          <Notice kind="error" className="mb-4">
            {error}
          </Notice>
        )}
        <AuthForm mode="signin" onModeChange={() => undefined} onDone={done} hideSwitch />
      </div>
      <p className="mt-4 text-center text-[13.5px]">
        <Link href="/" className="text-ink-3 hover:text-ink">
          Back to Amar Circular
        </Link>
      </p>
    </div>
  );
}
