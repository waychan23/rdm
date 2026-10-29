import type { CSSProperties } from "react";

import { token } from "@atlaskit/tokens";

/**
 * 1px ADS card border.
 *
 * Applied inline (not through cssMap) on purpose: @atlaskit/primitives' Box
 * ships a `border: none` reset whose stylesheet can load after our compiled
 * atoms in production, which resets border-width to `medium` and border-color
 * to `currentColor` (the thick black edge bug). Inline styles win regardless
 * of stylesheet order; hover background/focus outline still come from cssMap.
 */
export const cardBorder: CSSProperties = {
  border: `1px solid ${token("color.border")}`,
};
