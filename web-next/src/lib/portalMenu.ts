import type { CSSObjectWithLabel } from "@atlaskit/select";

/**
 * Select menus rendered inside ModalDialog/Drawer/overflow panels must portal
 * to <body> and sit above the modal overlay. Atlaskit's modal overlay uses
 * z-index 500/510 while react-select's portal defaults to 1, which makes the
 * options appear behind the dialog (looks like clicking does nothing).
 *
 * Spread these props into every Select used inside a dialog or clipped panel.
 * Keep `styles` narrow (only menuPortal) so it stays assignable to any typed
 * Select<Option, IsMulti> instance.
 */
export const portalMenuProps = {
  menuPortalTarget: document.body,
  menuPosition: "fixed" as const,
  styles: {
    menuPortal: (base: CSSObjectWithLabel): CSSObjectWithLabel => ({
      ...base,
      zIndex: 600,
    }),
  },
};
