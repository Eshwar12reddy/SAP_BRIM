import React from 'react';
import { GoogleSignInButton } from './GoogleSignInButton';
import { AuthDivider } from './AuthDivider';
import { GoogleAuthErrorBanner } from './GoogleAuthErrorBanner';

export const GoogleAuthSection: React.FC = () => {
  const isEnabled = import.meta.env.VITE_GOOGLE_LOGIN_ENABLED !== 'false';

  if (!isEnabled) {
    return null;
  }

  return (
    <div className="w-full">
      <GoogleAuthErrorBanner />
      <GoogleSignInButton />
      <AuthDivider />
    </div>
  );
};
