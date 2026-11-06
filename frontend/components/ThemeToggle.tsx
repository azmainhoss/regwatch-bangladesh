"use client";

import React, { useEffect, useState } from "react";
import { Sun, Moon } from "lucide-react";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem("theme") as "dark" | "light" | null;
    if (stored) {
      setTheme(stored);
      if (stored === "light") {
        document.documentElement.classList.remove("dark");
        document.documentElement.classList.add("light");
      } else {
        document.documentElement.classList.remove("light");
        document.documentElement.classList.add("dark");
      }
    } else {
      // Default to dark theme for Visual Direction 04
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("light");
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    localStorage.setItem("theme", nextTheme);
    if (nextTheme === "light") {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("light");
    } else {
      document.documentElement.classList.remove("light");
      document.documentElement.classList.add("dark");
    }
  };

  if (!mounted) {
    return (
      <button
        aria-label="Toggle theme"
        className="w-9 h-9 rounded-lg border border-tealNavy-700 bg-tealNavy-850 flex items-center justify-center text-slate-400"
      >
        <Moon className="w-4 h-4" />
      </button>
    );
  }

  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      className="w-9 h-9 rounded-lg border border-tealNavy-700 dark:border-tealNavy-700 light:border-slate-300 bg-tealNavy-850 dark:bg-tealNavy-850 light:bg-slate-100 hover:border-turquoise text-slate-300 dark:text-slate-300 light:text-slate-700 hover:text-turquoise transition flex items-center justify-center"
    >
      {theme === "dark" ? (
        <Sun className="w-4 h-4 text-turquoise" />
      ) : (
        <Moon className="w-4 h-4 text-tealNavy-900" />
      )}
    </button>
  );
}
