// Single i18next instance for the SPA (§17.115). Imported by main.tsx before
// the first render; `initAsync: false` makes resources available synchronously.
import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { clearPageCache } from "../lib/pageCache";
import { en } from "./resources/en";
import { zhCN } from "./resources/zh-CN";

export type Locale = "zh-CN" | "en";

export const SUPPORTED_LOCALES: Locale[] = ["zh-CN", "en"];
export const LOCALE_STORAGE_KEY = "rdm.locale";
export const DEFAULT_LOCALE: Locale = "zh-CN";

export function normalizeLocale(value: string | null | undefined): Locale {
  const tag = (value ?? "").toLowerCase();
  if (tag.startsWith("en")) return "en";
  if (tag.startsWith("zh")) return "zh-CN";
  return DEFAULT_LOCALE;
}

function detectLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (stored) return normalizeLocale(stored);
  } catch {
    // localStorage can be unavailable in privacy modes; fall through.
  }
  return normalizeLocale(typeof navigator === "undefined" ? undefined : navigator.language);
}

void i18n.use(initReactI18next).init({
  resources: {
    "zh-CN": zhCN,
    en,
  },
  lng: detectLocale(),
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: SUPPORTED_LOCALES,
  defaultNS: "common",
  ns: [
    "common",
    "nav",
    "labels",
    "auth",
    "workitems",
    "collab",
    "admin",
    "components",
    "projects",
    "sprints",
    "inbox",
    "mailbox",
    "members",
    "org",
    "item",
  ],
  initAsync: false,
  interpolation: { escapeValue: false },
  returnNull: false,
});

function syncDocumentLanguage(locale: string) {
  if (typeof document !== "undefined") {
    document.documentElement.lang = locale;
  }
}

i18n.on("languageChanged", syncDocumentLanguage);
syncDocumentLanguage(i18n.language);

/** Switch language, persist it, and drop cached localized list snapshots. */
export async function setLocale(locale: string): Promise<void> {
  const next = normalizeLocale(locale);
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, next);
  } catch {
    // Ignore storage failures; the in-memory language still changes.
  }
  clearPageCache();
  if (i18n.language !== next) {
    await i18n.changeLanguage(next);
  }
}

/** Value for the Accept-Language header on REST/SSE requests. */
export function apiLocale(): Locale {
  return normalizeLocale(i18n.language);
}

export { i18n };
