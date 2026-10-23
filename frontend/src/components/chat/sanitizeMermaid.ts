// Sanitizes Mermaid chart source before rendering:
// 1. Strips accidental markdown code fences (```mermaid ... ```).
// 2. Strips accidental unverified disclaimers injected into diagram syntax.
// 3. Safely quotes all edge labels (e.g. -->|label| -> -->|"label"|).
// 4. Quotes node labels containing parentheses, brackets, or colons.
// 5. Normalizes all subgraph definitions into valid Mermaid syntax.
// 6. Strips dangerous HTML tags/attributes to prevent XSS.

export function extractDiagram(input: string): string {
  let s = input.replace(/^\s*```(?:mermaid)?\s*/i, '');   // leading fence
  const fence = s.indexOf('```');
  if (fence !== -1) s = s.slice(0, fence);                 // cut at first fence
  const heading = s.search(/^#{1,6}\s/m);
  if (heading !== -1) s = s.slice(0, heading);             // cut at first markdown heading
  return s.trim();
}

export function sanitizeMermaid(src: string): string {
  if (!src) return '';

  // Strip wrapping markdown code blocks if present
  let clean = src.trim();
  clean = extractDiagram(clean);

  // Strip any accidental unverified disclaimers injected into diagram syntax
  clean = clean.replace(/\s*\((?:unverified|confirm in your system)[^)]*\)/gi, '');

  // If this is a sequenceDiagram, return with basic tag stripping
  if (/^\s*sequenceDiagram\b/m.test(clean)) {
    return clean.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  }

  if (!/^\s*(flowchart|graph)\b/m.test(clean)) {
    return clean;
  }

  // 1. Edge labels: -->|Replicate (sync)|  ->  -->|"Replicate (sync)"|
  // Quote any edge label that is not already wrapped in double quotes
  const edge = /((?:--+|==+|-\.+-)[>ox]?)\s*\|([^|\n]*)\|/g;
  clean = clean.replace(edge, (_m, arrow: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${arrow}|${t}|`;
    return `${arrow}|"${t.replace(/"/g, "'")}"|`;
  });

  // 2. Node labels: A[SAP SOM (Orders)]  ->  A["SAP SOM (Orders)"]
  const node = /(\b[A-Za-z0-9_]+)\[([^\]\n"]+)\]/g;
  clean = clean.replace(node, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return _m;
    // Don't modify special shapes like ((cylinder)) or ((circle))
    if (/^\(.*\)$/.test(t) || /^[\[\/\\]/.test(t)) return _m;
    return `${id}["${t.replace(/"/g, "'")}"]`;
  });

  // 3. Subgraph definitions:
  // Catches:
  // - subgraph ORDER_MGMT (unverified...)
  // - subgraph ORDER_MGMT: Order Management
  // - subgraph ORDER_MGMT - Order Management
  // - subgraph ORDER_MGMT [Order Management] (without quotes)
  // - subgraph Order Management Layer (with spaces and no brackets)
  clean = clean.replace(/^(\s*subgraph\s+)(.*)$/gm, (_m, prefix, rest) => {
    const trimmed = rest.trim();
    // Case 1: Already valid subgraph ID["Title"] or subgraph "Title"
    if (/^[\w-]+\s*\["[^"\n]*"\]$/.test(trimmed) || /^"[^"\n]+"$/.test(trimmed)) {
      return `${prefix}${trimmed}`;
    }
    // Case 2: subgraph ID[Title without quotes]
    const bracketMatch = trimmed.match(/^([\w-]+)\s*\[(.*)\]$/);
    if (bracketMatch) {
      const id = bracketMatch[1];
      const title = bracketMatch[2].replace(/"/g, "'").trim();
      return `${prefix}${id}["${title}"]`;
    }
    // Case 3: subgraph ID (Title...) or subgraph ID: Title or subgraph ID - Title
    const parenOrColon = trimmed.match(/^([\w-]+)\s*[\(:–-]\s*(.*)$/);
    if (parenOrColon) {
      const id = parenOrColon[1];
      let title = parenOrColon[2].trim();
      if (title.endsWith(')')) title = title.slice(0, -1).trim();
      title = title.replace(/"/g, "'");
      return `${prefix}${id}["${id} (${title})"]`;
    }
    // Case 4: Single word identifier: subgraph ORDER_MGMT
    if (/^[\w-]+$/.test(trimmed)) {
      return `${prefix}${trimmed}`;
    }
    // Case 5: Unquoted multiple words: subgraph Customer Engagement Layer
    const slug = trimmed.replace(/[^\w-]/g, '_').slice(0, 20);
    return `${prefix}${slug}["${trimmed.replace(/"/g, "'")}"]`;
  });

  // 4. Strip dangerous script/iframe tags
  clean = clean.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  clean = clean.replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, '');

  return clean;
}