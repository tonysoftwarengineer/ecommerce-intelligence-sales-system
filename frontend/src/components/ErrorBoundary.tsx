import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time crashes. Without this, a single bad value in a chart
 * unmounts the whole React tree and the user sees a blank white page with no
 * indication anything went wrong -- the frontend equivalent of a swallowed
 * exception.
 *
 * Must be a class component: React has no hook equivalent for
 * componentDidCatch.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Dashboard render failed:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="status status--error">
          <p className="status__title">Something went wrong</p>
          <p className="status__detail">
            The dashboard failed to render. This is a bug, not a connection problem.
          </p>
          <p className="status__detail status__detail--dim">{this.state.error.message}</p>
          <button
            type="button"
            className="status__button"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
