import { Component, type ErrorInfo, type ReactNode } from "react";

import Button from "@atlaskit/button/default/button";
import SectionMessage from "@atlaskit/section-message";
import { Box } from "@atlaskit/primitives/compiled";

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
      <Box padding="space.600" testId="error-boundary">
        <SectionMessage
          appearance="error"
          title="页面出错了"
          actions={
            <Button appearance="primary" onClick={() => window.location.reload()}>
              刷新页面
            </Button>
          }
        >
          {this.state.error.message || "渲染时发生未知错误。"}
        </SectionMessage>
      </Box>
    );
  }
}
