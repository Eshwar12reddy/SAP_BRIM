import React from 'react';

interface AuthDividerProps {
  label?: string;
  className?: string;
}

export const AuthDivider: React.FC<AuthDividerProps> = ({
  label = 'OR',
  className = '',
}) => {
  const isEnabled = import.meta.env.VITE_GOOGLE_LOGIN_ENABLED !== 'false';

  if (!isEnabled) {
    return null;
  }

  return (
    <div className={`relative my-4 flex items-center ${className}`} role="separator" aria-label={label}>
      <div className="grow border-t border-slate-200 dark:border-slate-700" />
      <span className="shrink-0 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
        {label}
      </span>
      <div className="grow border-t border-slate-200 dark:border-slate-700" />
    </div>
  );
};
