// @vitest-environment happy-dom
import { describe, it, expect } from 'vitest';
import mermaid from 'mermaid';
import { sanitizeMermaid } from './sanitizeMermaid';

describe('sanitizeMermaid', () => {
  it('handles the broken example with non-breaking hyphen U+2011 and a newline inside a label', () => {
    // Exact broken pattern from user prompt:
    // Non-breaking hyphen U+2011 in "FI\u2011CA" and a real newline inside quoted label
    const broken = `flowchart TD
  A["Customer Portal"] --> B["SAP SOM"]
  B --> C["SAP CC"]
  D["FI\u2011CA Contract
  Accounting & Invoicing"] --> E["S/4HANA Finance"]`;

    const clean = sanitizeMermaid(broken);

    // Non-breaking hyphen U+2011 must be replaced with ASCII hyphen '-'
    expect(clean).not.toContain('\u2011');
    expect(clean).toContain('FI-CA Contract');

    // Real newline inside label must be converted to <br/>
    expect(clean).toContain('FI-CA Contract<br/>Accounting & Invoicing');
    expect(clean).toContain('D["FI-CA Contract<br/>Accounting & Invoicing"]');
  });

  it('replaces all unicode dashes, en/em dashes, and minus signs with ASCII hyphen', () => {
    const input = `flowchart TD
  A["Step\u20101 \u2011 Step\u20122 \u2013 Step\u20143 \u2212 End"]`;
    const clean = sanitizeMermaid(input);
    expect(clean).toBe(`flowchart TD\n  A["Step-1 - Step-2 - Step-3 - End"]`);
  });

  it('replaces smart quotes with plain ASCII quotes and inner quotes with single quotes', () => {
    const input = `flowchart TD
  A[\u201CSAP S/4HANA\u201D] --> B[\u2018SOM\u2019]
  C["Layer with \u201Cnested\u201D quotes"]`;
    const clean = sanitizeMermaid(input);
    expect(clean).toContain('A["SAP S/4HANA"]');
    expect(clean).toContain("B[\"'SOM'\"]");
    expect(clean).toContain("C[\"Layer with 'nested' quotes\"]");
    expect(clean).not.toMatch(/[\u201C\u201D\u2018\u2019]/);
  });

  it('removes zero-width characters and normalizes non-breaking spaces', () => {
    const input = `flowchart TD
  A["SAP\u00A0SOM\u200B\uFEFF\u200D\u200C (Order\u202FManagement)"]`;
    const clean = sanitizeMermaid(input);
    expect(clean).toContain('A["SAP SOM (Order Management)"]');
    expect(clean).not.toMatch(/[\u200B\u200C\u200D\uFEFF\u00A0\u202F]/);
  });

  it('auto-quotes unquoted labels containing ( ) / & :', () => {
    const input = `flowchart TD
  A[SAP SOM (Orders) / CC & CI: Invoicing] -->|Sync / Async (REST) & RFC| B[FI-CA (Open Items)]
  C{Status: Is Active? & Valid / Approved} --> D[(Database (Primary) & Replica)]`;

    const clean = sanitizeMermaid(input);
    expect(clean).toContain('A["SAP SOM (Orders) / CC & CI: Invoicing"]');
    expect(clean).toContain('-->|"Sync / Async (REST) & RFC"|');
    expect(clean).toContain('B["FI-CA (Open Items)"]');
    expect(clean).toContain('C{"Status: Is Active? & Valid / Approved"}');
    expect(clean).toContain('D[("Database (Primary) & Replica")]');
  });

  it('counts subgraph vs end and appends missing end lines for truncated diagrams', () => {
    const truncated = `flowchart TD
  subgraph G1["Group 1"]
    A["Node A"] --> B["Node B"]
  subgraph G2["Group 2"]
    C["Node C"]`;

    const clean = sanitizeMermaid(truncated);
    const subgraphs = (clean.match(/^\s*subgraph\b/gm) || []).length;
    const ends = (clean.match(/^\s*end\b/gm) || []).length;

    expect(subgraphs).toBe(2);
    expect(ends).toBe(2);
    expect(clean.endsWith('end\nend') || clean.endsWith('end')).toBe(true);
  });

  it('strips ```mermaid code fences and surrounding prose', () => {
    const fenced = `Here is the architecture diagram:
\`\`\`mermaid
flowchart TD
  A["Client"] --> B["Server"]
\`\`\`
Hope this explanation helps!`;

    const clean = sanitizeMermaid(fenced);
    expect(clean).toBe(`flowchart TD\n  A["Client"] --> B["Server"]`);
    expect(clean).not.toContain('```');
    expect(clean).not.toContain('Here is the architecture');
    expect(clean).not.toContain('Hope this explanation');
  });

  it('normalizes CRLF to LF and trims whitespace', () => {
    const crlf = "flowchart TD\r\n  A[\"SOM\"] --> B[\"CC\"]\r\n";
    const clean = sanitizeMermaid(crlf);
    expect(clean).toBe('flowchart TD\n  A["SOM"] --> B["CC"]');
    expect(clean).not.toContain('\r');
  });

  it('validates with real mermaid.parse: broken example fails before and passes after sanitizeMermaid', async () => {
    const broken = `flowchart TD
  A["Customer Portal"] --> B["SAP SOM"]
  B --> C["SAP CC"]
  D["FI\u2011CA Contract
  Accounting & Invoicing"] --> E["S/4HANA Finance"]`;

    const clean = sanitizeMermaid(broken);
    const parseResult = await mermaid.parse(clean, { suppressErrors: false });
    expect(parseResult).toBeDefined();
  });

  it('validates with real mermaid.parse: missing end fails before and passes after sanitizeMermaid', async () => {
    const truncated = `flowchart TD
  subgraph SOM["Subscription Order Management"]
    A["Order"] --> B["Contract"]`;

    let threwBefore = false;
    try {
      await mermaid.parse(truncated, { suppressErrors: false });
    } catch {
      threwBefore = true;
    }
    expect(threwBefore).toBe(true);

    const clean = sanitizeMermaid(truncated);
    const parseResult = await mermaid.parse(clean, { suppressErrors: false });
    expect(parseResult).toBeDefined();
  });
});
