"use client";

import { MotionConfig } from "framer-motion";

/** reducedMotion="user" drops transform animations when the OS asks for less motion. */
export default function Providers({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
