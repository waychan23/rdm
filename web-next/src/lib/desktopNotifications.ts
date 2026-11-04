/**
 * Browser-native notifications for the realtime stream (RDM-130).
 *
 * The in-app bell already covers the visible tab, so a desktop notification is
 * only raised when the tab is hidden or the window is unfocused — the moment
 * the user is actually looking at something else. Delivery after the browser
 * has been closed needs the Push API plus a service worker, which this app
 * does not ship yet.
 *
 * Permission is per-origin and can only be requested from a user gesture, so
 * the toggle lives in the personal settings page.
 */

const ENABLED_KEY = "rdm.desktop-notifications";

export type DesktopNotificationState = "unsupported" | "insecure" | NotificationPermission;

function supported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function desktopNotificationState(): DesktopNotificationState {
  if (!supported()) return "unsupported";
  // Notifications are gated on a secure context; a LAN host served over plain
  // HTTP can never prompt, so say so instead of pretending the user blocked it.
  if (!window.isSecureContext) return "insecure";
  return Notification.permission;
}

/** Must be called from a user gesture (browser requirement). */
export async function requestDesktopNotificationPermission(): Promise<DesktopNotificationState> {
  if (!supported()) return "unsupported";
  if (!window.isSecureContext) return "insecure";
  if (Notification.permission === "granted") return "granted";
  // After an explicit block the browser resolves this immediately with
  // "denied" and shows nothing; there is no API to re-open its prompt.
  const state = await Notification.requestPermission();
  // Granting through this page is an explicit request to receive them, so do
  // not make the user flip a second switch.
  if (state === "granted") setDesktopNotificationsEnabled(true);
  return state;
}

export function desktopNotificationsEnabled(): boolean {
  if (desktopNotificationState() !== "granted") return false;
  try {
    return window.localStorage.getItem(ENABLED_KEY) !== "off";
  } catch {
    return true;
  }
}

export function setDesktopNotificationsEnabled(enabled: boolean): void {
  try {
    if (enabled) window.localStorage.removeItem(ENABLED_KEY);
    else window.localStorage.setItem(ENABLED_KEY, "off");
  } catch {
    // Storage can be unavailable (private mode); keep the default (enabled).
  }
}

export interface DesktopNotification {
  /** Collapses duplicates and stream-replayed events with the same id. */
  id: string;
  title: string;
  body?: string;
  /** Runs after the user clicks the notification. */
  onActivate?: () => void;
}

export function showDesktopNotification(notification: DesktopNotification): void {
  if (!desktopNotificationsEnabled()) return;
  if (document.visibilityState === "visible" && document.hasFocus()) return;
  try {
    const note = new Notification(notification.title, {
      body: notification.body,
      tag: notification.id,
    });
    note.onclick = () => {
      window.focus();
      note.close();
      notification.onActivate?.();
    };
  } catch {
    // A missed toast must never break the stream handler.
  }
}

/**
 * Show a notification right away, even while this tab is focused — used by the
 * settings page so the user can verify the permission and the OS channel.
 */
let testNotification: Notification | null = null;

export function sendTestDesktopNotification(title: string, body: string): boolean {
  if (desktopNotificationState() !== "granted") return false;
  try {
    const note = new Notification(title, {
      body,
      tag: "rdm-test-notification",
      // Keep it on screen until dismissed; a banner that auto-hides is easy to
      // miss while the user is looking at the settings page.
      requireInteraction: true,
    });
    // Some engines close a notification whose object is garbage-collected;
    // keep a reference until the user dismisses it.
    testNotification = note;
    note.onclose = () => {
      testNotification = null;
    };
    return true;
  } catch {
    return false;
  }
}
