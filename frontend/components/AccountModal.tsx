"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, LogOut } from "lucide-react";
import { AuthUser, logoutUser, openRegister } from "../services/api";
import { Modal, ModalHeader } from "./ui";
import AuthForm from "./AuthForm";

interface AccountModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: AuthUser | null;
  onUserChange: (user: AuthUser | null) => void;
}

export default function AccountModal({ isOpen, onClose, currentUser, onUserChange }: AccountModalProps) {
  const [mode, setMode] = useState<"signin" | "signup">("signin");

  // Signed out: "Sign in" anywhere in the app opens the one Register / Sign in dialog instead.
  useEffect(() => {
    if (isOpen && !currentUser) {
      openRegister("register");
      onClose();
    }
  }, [isOpen, currentUser, onClose]);

  const handleLogout = () => {
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
                ? "Sign in to your Amar Circular account."
                : "It takes a few seconds. You will be signed in at once."
            }
            onClose={onClose}
          />
          <div className="px-5 py-5">
            <AuthForm
              mode={mode}
              onModeChange={(m) => {
                // Registering always uses the 3-step sign-up.
                if (m === "signup") {
                  onClose();
                  openRegister("register");
                } else setMode(m);
              }}
              onDone={(user) => {
                onUserChange(user);
                setMode("signin");
                onClose();
              }}
            />
          </div>
        </>
      )}
    </Modal>
  );
}
