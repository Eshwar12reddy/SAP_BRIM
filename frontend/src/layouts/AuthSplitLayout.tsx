import React from 'react';
import './AuthSplitLayout.css';

interface AuthSplitLayoutProps {
  children: React.ReactNode;
}

export const AuthSplitLayout: React.FC<AuthSplitLayoutProps> = ({ children }) => {
  return (
    <div className="auth-split-layout min-h-screen w-full flex flex-col min-[900px]:flex-row bg-[#FFFFFF]">
      {/* Left Column (~55% at >=900px): Solid white #FFFFFF, filling full height and width */}
      <div className="auth-split-left w-full min-[900px]:w-[55%] flex flex-col min-h-screen bg-[#FFFFFF]">
        {children}
      </div>

      {/* Right Column (~45% at >=900px): Dark Navy Panel with code pattern, headline & line-art illustration */}
      <aside
        aria-label="Clyptus.Ai platform showcase"
        className="hidden min-[900px]:flex w-[45%] min-h-screen bg-[#13283A] text-white flex-col items-center justify-center relative overflow-hidden p-8 lg:p-12 select-none"
      >
        {/* Background: Faint, low-opacity repeating pattern of code symbols: ( ) { } [ ] ; </> */}
        <div
          aria-hidden="true"
          className="absolute inset-0 opacity-[0.07] pointer-events-none flex flex-col justify-around overflow-hidden font-mono text-xs text-slate-300 leading-loose tracking-widest p-6"
        >
          {Array.from({ length: 14 }).map((_, i) => (
            <div key={i} className="whitespace-nowrap">
              {'( )  { }  [ ]  ;  </>    ( )  { }  [ ]  ;  </>    ( )  { }  [ ]  ;  </>    ( )  { }  [ ]  ;  </>'}
            </div>
          ))}
        </div>

        {/* Decorative ambient gradient ring */}
        <div
          aria-hidden="true"
          className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl pointer-events-none"
        />
        <div
          aria-hidden="true"
          className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-orange-500/10 blur-3xl pointer-events-none"
        />

        {/* Foreground Content */}
        <div className="relative z-10 max-w-md w-full flex flex-col items-center text-center">
          {/* Headline: Large white bold two-line centered headline */}
          <h2 className="text-3xl lg:text-4xl font-bold tracking-tight text-white leading-snug mb-8">
            Get SAP answers<br />
            <span className="text-slate-100">faster and smarter</span>
          </h2>

          {/* Original Line-Art Illustration */}
          <div className="w-full max-w-[340px] aspect-4/3 relative flex items-center justify-center">
            <svg
              viewBox="0 0 360 270"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="w-full h-full drop-shadow-md"
              aria-label="Illustration representing intelligent conversational SAP knowledge network"
              role="img"
            >
              {/* Background ambient mesh grid lines */}
              <path
                d="M40 70H320M40 135H320M40 200H320"
                stroke="#2A435C"
                strokeWidth="1"
                strokeDasharray="4 6"
                strokeOpacity="0.5"
              />
              <path
                d="M90 30V240M180 30V240M270 30V240"
                stroke="#2A435C"
                strokeWidth="1"
                strokeDasharray="4 6"
                strokeOpacity="0.5"
              />

              {/* Connecting network lines between nodes */}
              <path
                d="M80 160L140 100M140 100L220 100M220 100L280 150M140 100L180 170M220 100L180 170"
                stroke="#4B6B8A"
                strokeWidth="2"
                strokeLinecap="round"
              />

              {/* Primary Chat Bubble (Left/User Query) */}
              <g transform="translate(45, 125)">
                <rect
                  x="0"
                  y="0"
                  width="100"
                  height="54"
                  rx="12"
                  fill="#1C3850"
                  stroke="#476E92"
                  strokeWidth="1.5"
                />
                {/* Simulated text lines */}
                <line x1="16" y1="18" x2="84" y2="18" stroke="#8EA9C4" strokeWidth="2.5" strokeLinecap="round" />
                <line x1="16" y1="28" x2="65" y2="28" stroke="#8EA9C4" strokeWidth="2.5" strokeLinecap="round" />
                <line x1="16" y1="38" x2="74" y2="38" stroke="#8EA9C4" strokeWidth="2" strokeLinecap="round" />
                {/* Pointer tail */}
                <path d="M70 54L80 64V54H70Z" fill="#1C3850" stroke="#476E92" strokeWidth="1.5" />
              </g>

              {/* Assistant Knowledge Chat Bubble (Center/Top) with Orange Accent Fill #F4562B */}
              <g transform="translate(130, 45)">
                <rect
                  x="0"
                  y="0"
                  width="130"
                  height="65"
                  rx="14"
                  fill="#1E3D56"
                  stroke="#5C86AE"
                  strokeWidth="1.5"
                />
                {/* Distinctive Orange Accent Badge */}
                <circle cx="24" cy="24" r="8" fill="#F4562B" />
                <path d="M21 24H27M24 21V27" stroke="#FFFFFF" strokeWidth="1.5" strokeLinecap="round" />
                {/* Structured response lines */}
                <line x1="38" y1="22" x2="112" y2="22" stroke="#FFFFFF" strokeWidth="2.5" strokeLinecap="round" />
                <line x1="38" y1="30" x2="95" y2="30" stroke="#ADC8E2" strokeWidth="2" strokeLinecap="round" />
                <line x1="18" y1="42" x2="112" y2="42" stroke="#7E9EB8" strokeWidth="2" strokeLinecap="round" />
                <line x1="18" y1="50" x2="80" y2="50" stroke="#7E9EB8" strokeWidth="2" strokeLinecap="round" />
              </g>

              {/* Connected Knowledge Nodes */}
              {/* Node 1 */}
              <circle cx="140" cy="100" r="7" fill="#13283A" stroke="#60A5FA" strokeWidth="2.5" />
              <circle cx="140" cy="100" r="2.5" fill="#60A5FA" />

              {/* Node 2 */}
              <circle cx="220" cy="100" r="7" fill="#13283A" stroke="#60A5FA" strokeWidth="2.5" />
              <circle cx="220" cy="100" r="2.5" fill="#60A5FA" />

              {/* Central Synthesis Hub Node */}
              <circle cx="180" cy="170" r="10" fill="#1C3850" stroke="#F4562B" strokeWidth="2.5" />
              <circle cx="180" cy="170" r="4" fill="#F4562B" />

              {/* Verified Output Node (Right) */}
              <g transform="translate(230, 135)">
                <rect
                  x="0"
                  y="0"
                  width="95"
                  height="50"
                  rx="10"
                  fill="#193348"
                  stroke="#476E92"
                  strokeWidth="1.5"
                />
                <circle cx="20" cy="20" r="6" fill="#38BDF8" fillOpacity="0.2" stroke="#38BDF8" strokeWidth="1.5" />
                <path d="M18 20L20 22L23 18" stroke="#38BDF8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                <line x1="32" y1="20" x2="82" y2="20" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" />
                <line x1="16" y1="34" x2="75" y2="34" stroke="#8EA9C4" strokeWidth="2" strokeLinecap="round" />
              </g>

              {/* Small "+" Stars */}
              {/* Star 1 */}
              <g transform="translate(100, 35)">
                <path d="M0 -5V5M-5 0H5" stroke="#F4562B" strokeWidth="1.75" strokeLinecap="round" />
              </g>
              {/* Star 2 */}
              <g transform="translate(280, 75)">
                <path d="M0 -6V6M-6 0H6" stroke="#FFFFFF" strokeWidth="1.75" strokeLinecap="round" />
              </g>
              {/* Star 3 */}
              <g transform="translate(70, 220)">
                <path d="M0 -4V4M-4 0H4" stroke="#60A5FA" strokeWidth="1.5" strokeLinecap="round" />
              </g>
              {/* Star 4 */}
              <g transform="translate(295, 210)">
                <path d="M0 -5V5M-5 0H5" stroke="#F4562B" strokeWidth="1.75" strokeLinecap="round" />
              </g>
              {/* Star 5 */}
              <g transform="translate(195, 235)">
                <path d="M0 -4V4M-4 0H4" stroke="#FFFFFF" strokeWidth="1.5" strokeLinecap="round" />
              </g>
            </svg>
          </div>
        </div>
      </aside>
    </div>
  );
};
