"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Plans are gone (everything is free); old links go to the dashboard. */
export default function PlansRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
