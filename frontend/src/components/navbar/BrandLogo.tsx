import React from 'react';
import { Link } from 'react-router-dom';
import fullLogoWhite from '../../assets/clyptusap-logo.png';
import fullLogoDark from '../../assets/clyptusap-logo-darktext.png';
import iconOnly from '../../assets/clyptusap-icon.png';

interface BrandLogoProps {
  compact?: boolean;
  light?: boolean;
}

export const BrandLogo: React.FC<BrandLogoProps> = ({ compact = false, light = false }) => {
  if (compact) {
    return (
      <Link className="brand inline-flex items-center" to="/" aria-label="Clyptus.Ai home">
        <img className="h-8 w-8 object-contain drop-shadow-sm" src={iconOnly} alt="Clyptus.Ai" />
      </Link>
    );
  }

  return (
    <Link className={`brand inline-flex items-center gap-2.5 ${light ? 'brand-light' : ''}`} to="/" aria-label="Clyptus.Ai home">
      {/* On dark surfaces show white text version; on light surfaces show dark text version */}
      <img
        className={`h-8 w-auto object-contain ${light ? 'hidden' : 'dark:hidden'}`}
        src={fullLogoDark}
        alt="Clyptus.Ai"
      />
      <img
        className={`h-8 w-auto object-contain ${light ? 'block' : 'hidden dark:block'}`}
        src={fullLogoWhite}
        alt="Clyptus.Ai"
      />
    </Link>
  );
};
