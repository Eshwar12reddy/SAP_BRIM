import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AlertCircle, X } from 'lucide-react';

interface GoogleAuthErrorBannerProps {
  className?: string;
}

export const GoogleAuthErrorBanner: React.FC<GoogleAuthErrorBannerProps> = ({ className = '' }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const errorCode = searchParams.get('error');
  const [dismissed, setDismissed] = useState(false);

  // If a new error parameter appears, reset dismissal state
  useEffect(() => {
    if (errorCode) {
      setDismissed(false);
    }
  }, [errorCode]);

  if (!errorCode || dismissed) {
    return null;
  }

  const errorMessage =
    errorCode === 'access_denied'
      ? 'Google sign-in was cancelled.'
      : 'Google sign-in failed. Please try again.';

  const handleDismiss = () => {
    setDismissed(true);
    // Remove the error parameter from URL without full reload or losing other params
    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('error');
    setSearchParams(nextParams, { replace: true });
  };

  return (
    <div
      role="alert"
      aria-live="polite"
      className={`mb-3 p-3 rounded-xl bg-amber-50 border border-amber-200 dark:bg-amber-950/60 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-200 flex items-center justify-between gap-2 text-left shadow-2xs ${className}`}
    >
      <div className="flex items-center gap-2">
        <AlertCircle className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" />
        <span className="font-medium">{errorMessage}</span>
      </div>
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Dismiss Google sign-in notification"
        className="p-1 rounded-md text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/60 focus:outline-none focus:ring-2 focus:ring-amber-500 transition-colors cursor-pointer"
      >
        <X className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
    </div>
  );
};
