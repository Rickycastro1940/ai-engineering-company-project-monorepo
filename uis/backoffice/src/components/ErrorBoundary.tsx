import { Component, type ErrorInfo, type ReactNode } from "react";
import "../pages/AuthPages.css";

type Props = { children: ReactNode };
type State = { hasError: boolean; message: string };

/** Catches render crashes so staff still see a recovery path instead of a blank page. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || "Something went wrong." };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Backoffice render error", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <main className="auth-shell">
          <section className="auth-card" role="alert">
            <p className="auth-card__eyebrow">Brasaland Digital</p>
            <h1>This view failed to load</h1>
            <p className="auth-card__lead">{this.state.message}</p>
            <button type="button" onClick={() => window.location.reload()}>
              Reload
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
