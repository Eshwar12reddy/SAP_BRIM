import React from 'react';
import { motion } from 'framer-motion';
import iconOnly from '../../assets/clyptusap-icon.png';

interface WelcomeScreenProps {
  onSelectPrompt?: (prompt: string) => void;
}

export const WelcomeScreen: React.FC<WelcomeScreenProps> = () => {
  return (
    <div className="chat-empty w-full max-w-3xl mx-auto text-center px-4 pt-4 pb-6">
      {/* Brand Icon */}
      <motion.div
        className="mx-auto mb-3 w-12 h-12 flex items-center justify-center"
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.4 }}
      >
        <img src={iconOnly} alt="Clyptus.Ai" className="w-10 h-10 object-contain" />
      </motion.div>

      <div className="tracking-widest text-[11px] font-semibold text-slate-500 uppercase mb-1">
        SAP BRIM KNOWLEDGE ASSISTANT
      </div>

      <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-[#0F172A] dark:text-white">
        Ask about <span className="text-[#38BDF8]">SAP.</span>
      </h1>
    </div>
  );
};


