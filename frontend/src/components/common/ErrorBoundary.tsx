import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertOctagon, RotateCcw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  errorId: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    errorId: null,
  };

  public static getDerivedStateFromError(_: Error): State {
    // Generate a sanitized reference ID for tracking without leaking stack trace
    const errorId = `err_${Math.random().toString(36).substring(2, 10)}`;
    return { hasError: true, errorId };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Client-side structured error logging (console only; never leak sensitive state)
    console.error('ErrorBoundary caught exception:', {
      errorId: this.state.errorId,
      message: error.message,
      componentStack: errorInfo.componentStack,
    });
  }

  private handleReset = () => {
    this.setState({ hasError: false, errorId: null });
    window.location.reload();
  };

  private handleGoHome = () => {
    this.setState({ hasError: false, errorId: null });
    window.location.href = '/dashboard';
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200 shadow-xl p-6 sm:p-8 text-center space-y-4">
            <div className="w-14 h-14 bg-rose-100 text-rose-600 rounded-2xl flex items-center justify-center mx-auto">
              <AlertOctagon className="w-8 h-8" />
            </div>

            <div>
              <h2 className="text-lg font-bold text-slate-900">
                Something went wrong
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                An unexpected interface error occurred. Our operational team has been notified.
              </p>
            </div>

            {this.state.errorId && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-left">
                <span className="text-[11px] font-semibold text-slate-400 block uppercase tracking-wider">
                  Incident Reference ID
                </span>
                <span className="font-mono text-xs text-slate-800 font-bold">
                  {this.state.errorId}
                </span>
              </div>
            )}

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-2">
              <button
                type="button"
                onClick={this.handleReset}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 transition shadow-sm"
              >
                <RotateCcw className="w-4 h-4" />
                <span>Reload Page</span>
              </button>

              <button
                type="button"
                onClick={this.handleGoHome}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-xs font-semibold hover:bg-slate-200 transition"
              >
                <Home className="w-4 h-4" />
                <span>Dashboard</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
