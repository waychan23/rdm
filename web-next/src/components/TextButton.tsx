import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";

import { token } from "@atlaskit/tokens";

// Inline text action used where the new Button has no "link" appearance
// (downloads, deletes, edit links). ADS tokens only.
interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  danger?: boolean;
  children: ReactNode;
}

export default function TextButton({ danger, children, style, ...rest }: Props) {
  const base: CSSProperties = {
    background: "none",
    border: "none",
    padding: 0,
    font: "inherit",
    cursor: "pointer",
    color: danger ? token("color.text.danger") : token("color.link"),
  };
  return (
    <button type="button" style={{ ...base, ...style }} {...rest}>
      {children}
    </button>
  );
}
