// Outbound email settings (SMTP) and the test-send probe.

import { api } from "../lib/api";
import type { EmailSettings } from "../types";

export function getEmailSettings(): Promise<EmailSettings> {
  return api.get<EmailSettings>("/email-settings").then((res) => res.data);
}

export function updateEmailSettings(payload: Record<string, unknown>): Promise<void> {
  return api.patch("/email-settings", payload).then(() => undefined);
}

export function sendTestEmail(to: string | null): Promise<{ sent: boolean; to: string }> {
  return api
    .post<{ sent: boolean; to: string }>("/email-settings/test", { to })
    .then((res) => res.data);
}
