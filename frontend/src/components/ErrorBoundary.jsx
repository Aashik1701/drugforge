// Error Boundary Component
import React from 'react';
import { AlertCircle } from 'lucide-react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { 
      hasError: false,
      error: null,
      errorInfo: null
    };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the fallback UI
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Log the error to an error reporting service
    console.error("Error caught by ErrorBoundary:", error, errorInfo);
    this.setState({ errorInfo });
    
    // You could also log the error to an analytics service here
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  render() {
    const { hasError, error } = this.state;
    const { fallback, children } = this.props;
    
    if (hasError) {
      // Render custom fallback UI if provided
      if (fallback) {
        return fallback(error);
      }
      
      // Default fallback UI
      return (
        <div className="p-6 bg-red-50 border border-red-200 rounded-lg my-4">
          <div className="flex items-center">
            <AlertCircle className="text-red-600 mr-2" size={24} />
            <h2 className="text-lg font-semibold text-red-700">
              Something went wrong
            </h2>
          </div>
          <div className="mt-2 text-sm text-gray-700">
            <p>This component failed to render properly.</p>
            {error && error.message && (
              <details className="mt-2 bg-white p-2 rounded border border-red-100">
                <summary className="font-medium cursor-pointer">Error details</summary>
                <p className="mt-1 font-mono text-xs whitespace-pre-wrap text-red-600">{error.message}</p>
              </details>
            )}
          </div>
          <div className="mt-4">
            <button
              onClick={() => this.setState({ hasError: false })}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return children;
  }
}

export default ErrorBoundary;
