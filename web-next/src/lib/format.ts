const pad = (n: number) => String(n).padStart(2, "0");

function parse(iso?: string | null): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * RFC 3339 timestamp (API always sends UTC with an offset) → local
 * "YYYY-MM-DD HH:mm:ss"; "—" for missing/invalid input.
 */
export function formatDate(iso?: string | null): string {
  const d = parse(iso);
  if (!d) return "—";
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Hours input keeps the raw string while editing so the controlled field does
 * not swallow "0." / leading zeros (RDM-28). Only digits and one decimal dot
 * with a single fractional digit survive.
 */
export function sanitizeHoursInput(raw: string): string {
  const cleaned = raw.replace(/[^\d.]/g, "");
  const dot = cleaned.indexOf(".");
  if (dot < 0) return cleaned;
  const fraction = cleaned.slice(dot + 1).replace(/\./g, "").slice(0, 1);
  return `${cleaned.slice(0, dot)}.${fraction}`;
}

/** Raw hours input → API number; blank means 0 for the create/edit dialogs. */
export function parseHoursInput(raw: string): number {
  const text = raw.trim();
  if (!text) return 0;
  const value = Number(text);
  return Number.isFinite(value) ? value : 0;
}
