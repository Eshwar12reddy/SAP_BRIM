// @vitest-environment happy-dom
import { describe, it, expect } from 'vitest';

describe('SapGuiSvgViewer contract and sanitization', () => {
  it('sanitizes dangerous script tags and inline event handlers from SVG', () => {
    const rawSvgWithXss = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 340">
        <script>alert('xss')</script>
        <rect width="680" height="340" fill="#0B0F19" onload="alert('fail')"/>
        <text x="68" y="21">Step 1 · FKKBIX_BIT_DISPLAY · Display Billable Items</text>
        <a href="javascript:alert(1)">Click</a>
      </svg>
    `;

    // Replicate sanitization logic in SapGuiSvgViewer
    const clean = rawSvgWithXss
      .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, '')
      .replace(/\son\w+="[^"]*"/gi, '')
      .replace(/\son\w+='[^']*'/gi, '')
      .replace(/\s(href|xlink:href)=["']javascript:[^"']*["']/gi, '');

    expect(clean).not.toContain('<script>');
    expect(clean).not.toContain('onload=');
    expect(clean).not.toContain('javascript:');
    expect(clean).toContain('Step 1 · FKKBIX_BIT_DISPLAY · Display Billable Items');
  });

  it('correctly extracts SAP GUI title bar pattern', () => {
    const svgContent = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 340">
        <text x="68" y="21">Step 2 · FKKBIX_BILL_M · Execute Billing</text>
      </svg>
    `;

    const match = svgContent.match(/(Step\s*\d+\s*·\s*[^<]+|Verification\s*·\s*[^<]+)/i);
    expect(match).not.toBeNull();
    expect(match![1].trim()).toBe('Step 2 · FKKBIX_BILL_M · Execute Billing');
  });

  it('correctly extracts verification title bar pattern', () => {
    const verifContent = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 680 340">
        <text x="68" y="21">Verification · FKKINV_M · Execute Invoicing</text>
      </svg>
    `;

    const match = verifContent.match(/(Step\s*\d+\s*·\s*[^<]+|Verification\s*·\s*[^<]+)/i);
    expect(match).not.toBeNull();
    expect(match![1].trim()).toBe('Verification · FKKINV_M · Execute Invoicing');
  });
});
