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

export type DesktopNotificationState = "unsupported" | NotificationPermission;

function supported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export function desktopNotificationState(): DesktopNotificationState {
  if (!supported()) return "unsupported";
  return Notification.permission;
}

/** Must be called from a user gesture (browser requirement). */
export async function requestDesktopNotificationPermission(): Promise<DesktopNotificationState> {
  if (!supported()) return "unsupported";
  if (Notification.permission !== "default") return Notification.permission;
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
