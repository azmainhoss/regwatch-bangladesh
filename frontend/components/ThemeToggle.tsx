"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Moon, Sun } from "lucide-react";

type Theme = "light" | "dark";
const STORAGE_KEY = "theme";

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

/** Light by default. The choice is remembered in localStorage under "theme". */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(STORAGE_KEY);
    } catch {
      stored = null;
    }
    setTheme(stored === "dark" ? "dark" : "light");
    // Other open tabs follow a change at once.
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      const next: Theme = e.newValue === "dark" ? "dark" : "light";
      setTheme(next);
      applyTheme(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode: the choice lasts for this page only */
    }
  };

  const label = theme === "dark" ? "Switch to light mode" : "Switch to dark mode";

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className="relative grid h-11 w-9 sm:h-9 place-items-center overflow-hidden rounded-control border border-line text-ink-2 transition-colors hover:border-line-strong hover:bg-sunken hover:text-ink"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ opacity: 0, rotate: -45, scale: 0.6 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          exit={{ opacity: 0, rotate: 45, scale: 0.6 }}
          transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          className="grid place-items-center"
        >
          {theme === "dark" ? <Sun className="h-4 w-4" strokeWidth={1.75} /> : <Moon className="h-4 w-4" strokeWidth={1.75} />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
