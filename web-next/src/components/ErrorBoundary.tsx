import { Component, type ErrorInfo, type ReactNode } from "react";

import Button from "@atlaskit/button/default/button";
import { cssMap } from "@atlaskit/css";
import SectionMessage from "@atlaskit/section-message";
import { Box } from "@atlaskit/primitives/compiled";

import { i18n } from "../i18n";

const styles = cssMap({
  padded: { padding: "var(--ds-space-600)" },
});

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Last-resort guard so a render error does not leave a blank page. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep the stack in the console for local diagnosis; the UI stays usable.
    console.error("Unhandled render error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <Box xcss={styles.padded} testId="error-boundary">
        <SectionMessage
          appearance="error"
          title={i18n.t("error.pageError", { ns: "common" })}
          actions={
            <Button appearance="primary" onClick={() => window.location.reload()}>
              {i18n.t("error.reloadPage", { ns: "common" })}
            </Button>
          }
        >
          {this.state.error.message || i18n.t("error.renderError", { ns: "common" })}
        </SectionMessage>
      </Box>
    );
  }
}
