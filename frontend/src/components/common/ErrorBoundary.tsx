/*
 * Top-level crash guard. Without this, an uncaught render error anywhere in
 * the tree unmounts the whole app and leaves the user staring at a blank
 * page (or, in dev, a raw stack trace) with no way back except a hard
 * reload. This catches it, shows a plain-language message, and offers a
 * reload action instead.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("Unhandled UI error:", error, info.componentStack);
  }

  private handleReload = (): void => {
    this.setState({ error: null });
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.error) {
      return this.props.children;
    }
    return (
      <div
        role="alert"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1rem",
          minHeight: "100vh",
          padding: "2rem",
          textAlign: "center",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <h1 style={{ fontSize: "1.25rem", margin: 0 }}>Something went wrong</h1>
        <p style={{ maxWidth: "32rem", opacity: 0.8, margin: 0 }}>
          The app hit an unexpected error and couldn&apos;t continue. Your original photo hasn&apos;t
          been modified. Reloading usually fixes this.
        </p>
        <button
          type="button"
          onClick={this.handleReload}
          style={{
            padding: "0.5rem 1.25rem",
            borderRadius: "0.5rem",
            border: "1px solid currentColor",
            background: "transparent",
            cursor: "pointer",
            font: "inherit",
          }}
        >
          Reload
        </button>
      </div>
    );
  }
}
