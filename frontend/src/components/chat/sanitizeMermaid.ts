// Sanitizes Mermaid chart source before validation and rendering:
// 1. Strips markdown fences (```mermaid ... ```) and surrounding prose.
// 2. Replaces Unicode hyphens/dashes (U+2010..U+2014, U+2212) with standard ASCII '-'.
// 3. Replaces smart quotes with ASCII quotes; converts nested inner quotes to single quotes.
// 4. Removes zero-width characters and normalizes non-breaking spaces.
// 5. Converts real newlines inside quoted or bracketed labels to <br/>.
// 6. Auto-quotes unquoted labels containing ( ) / & : or special characters.
// 7. Normalizes subgraph definitions and appends missing 'end' statements for truncated diagrams.
// 8. Normalizes CRLF to LF, strips unsafe script/iframe tags, and trims.

export function extractDiagram(input: string): string {
  if (!input || typeof input !== 'string') return '';
  let s = input.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();

  // 1. Extract content from between ```mermaid and ```
  const fenceMatch = s.match(/```(?:mermaid)?\s*\n?([\s\S]*?)```/i);
  if (fenceMatch) {
    s = fenceMatch[1].trim();
  } else {
    // Strip leading fence if unclosed
    s = s.replace(/^\s*```(?:mermaid)?\s*/i, '');
    const firstFence = s.indexOf('```');
    if (firstFence !== -1) {
      s = s.slice(0, firstFence);
    }
  }

  // 2. Strip surrounding prose before the diagram keyword
  const diagramKeywords = [
    'flowchart',
    'graph',
    'sequenceDiagram',
    'classDiagram',
    'stateDiagram-v2',
    'stateDiagram',
    'erDiagram',
    'journey',
    'gantt',
    'pie',
    'gitGraph',
    'C4Context',
    'mindmap',
    'timeline',
    'quadrantChart',
    'architecture-beta',
    'packet-beta',
    'kanban',
    'block-beta'
  ];
  const keywordRegex = new RegExp(`^\\s*(?:${diagramKeywords.join('|')})\\b`, 'im');
  const kwMatch = s.match(keywordRegex);
  if (kwMatch && kwMatch.index !== undefined && kwMatch.index > 0) {
    s = s.slice(kwMatch.index);
  }

  // 3. Cut at trailing markdown heading if any
  const heading = s.search(/\n#{1,6}\s/);
  if (heading !== -1) {
    s = s.slice(0, heading);
  }

  return s.trim();
}

export function sanitizeMermaid(src: string): string {
  if (!src || typeof src !== 'string') return '';

  // 1. Normalize line endings and extract pure diagram code
  let clean = src.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
  clean = extractDiagram(clean);
  if (!clean) return '';

  // 2. Unicode normalization:
  // Hyphens / Dashes: U+2010, U+2011, U+2012, U+2013, U+2014, U+2212 -> '-'
  clean = clean.replace(/[\u2010\u2011\u2012\u2013\u2014\u2212]/g, '-');

  // Smart quotes:
  // Double quotes -> '"'
  clean = clean.replace(/[\u201C\u201D\u201E\u201F\u00AB\u00BB]/g, '"');
  // Single quotes -> "'"
  clean = clean.replace(/[\u2018\u2019\u201A\u201B\u0060]/g, "'");

  // Non-breaking and special spaces -> regular space ' '
  clean = clean.replace(/[\u00A0\u202F\u2007]/g, ' ');

  // Zero-width characters (ZWSP, ZWNJ, ZWJ, BOM, LRM, RLM) -> remove
  clean = clean.replace(/[\u200B\u200C\u200D\uFEFF\u200E\u200F]/g, '');

  // Strip unverified disclaimers mistakenly injected into diagram syntax
  clean = clean.replace(/\s*\((?:unverified|confirm in your system)[^)]*\)/gi, '');

  // 3. Convert real newlines inside quoted labels / bracketed labels to <br/>
  // This targets any node labels ["... \n ..."], (["... \n ..."]), etc.
  clean = clean.replace(/\["([\s\S]*?)"\]/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `["${formatted}"]`;
  });
  clean = clean.replace(/\(\["([\s\S]*?)"\]\)/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `(["${formatted}"])`;
  });
  clean = clean.replace(/\[\("([\s\S]*?)"\)\]/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `[("${formatted}")]`;
  });
  clean = clean.replace(/\[\["([\s\S]*?)"\]\]/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `[["${formatted}"]]`;
  });
  clean = clean.replace(/\{\{"([\s\S]*?)"\}\}/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `{{ "${formatted}" }}`;
  });
  clean = clean.replace(/\(\("([\s\S]*?)"\)\)/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `(("${formatted}"))`;
  });
  clean = clean.replace(/\("([\s\S]*?)"\)/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `("${formatted}")`;
  });
  clean = clean.replace(/\{"([\s\S]*?)"\}/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `{"${formatted}"}`;
  });
  clean = clean.replace(/\|"([\s\S]*?)"\|/g, (_m, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>');
    return `|"${formatted}"|`;
  });

  // Catch unquoted bracket contents that contain newlines
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\[([^\]\n]*\n[^\]]*)\]/g, (_m, id: string, inner: string) => {
    const formatted = inner.replace(/\n\s*/g, '<br/>').replace(/"/g, "'").trim();
    return `${id}["${formatted}"]`;
  });

  // 4. Edge labels: -->|label| -> -->|"label"|
  // Quotes any edge label not already wrapped in double quotes, and converts inner double quotes to single quotes
  const edge = /((?:--+|==+|-\.+-)[>ox]?)\s*\|([^|\n]*)\|/g;
  clean = clean.replace(edge, (_m, arrow: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (t.startsWith('"') && t.endsWith('"') && t.length >= 2) {
      const inner = t.slice(1, -1).replace(/"/g, "'");
      return `${arrow}|"${inner}"|`;
    }
    return `${arrow}|"${t.replace(/"/g, "'")}"|`;
  });

  // 5. Convert inner double quotes inside quoted labels to single quotes
  clean = clean.replace(/\["([\s\S]*?)"\]/g, (_m, inner: string) => {
    return `["${inner.replace(/"/g, "'")}"]`;
  });

  // 6. Auto-quote unquoted node labels:
  // Stadium shape: A([Label]) -> A(["Label"])
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\(\[([\s\S]*?)\]\)/g, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${id}(["${t.slice(1, -1).replace(/"/g, "'")}"])`;
    return `${id}(["${t.replace(/"/g, "'")}"])`;
  });

  // Cylinder shape: A[(Database)] -> A[("Database")]
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\[\(([\s\S]*?)\)\]/g, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${id}[("${t.slice(1, -1).replace(/"/g, "'")}")]`;
    return `${id}[("${t.replace(/"/g, "'")}")]`;
  });

  // Subroutine shape: A[[Label]] -> A[["Label"]]
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\[\[([\s\S]*?)\]\]/g, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${id}[["${t.slice(1, -1).replace(/"/g, "'")}"]]`;
    return `${id}[["${t.replace(/"/g, "'")}"]]`;
  });

  // Hexagon shape: A{{Label}} -> A{{"Label"}}
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\{\{([\s\S]*?)\}\}/g, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${id}{{"${t.slice(1, -1).replace(/"/g, "'")}"}}`;
    return `${id}{{"${t.replace(/"/g, "'")}"}}`;
  });

  // Circle shape: A((Label)) -> A(("Label"))
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\(\(([\s\S]*?)\)\)/g, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${id}(("${t.slice(1, -1).replace(/"/g, "'")}"))`;
    return `${id}(("${t.replace(/"/g, "'")}"))`;
  });

  // Rhombus / Decision: A{Label} -> A{"Label"}
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\{([^}{}\n]+)\}/g, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${id}{"${t.slice(1, -1).replace(/"/g, "'")}"}`;
    return `${id}{"${t.replace(/"/g, "'")}"}`;
  });

  // Standard rectangle: A[Label] -> A["Label"]
  clean = clean.replace(/(\b[A-Za-z0-9_]+\s*)\[([^\]\n]+)\]/g, (_m, id: string, label: string) => {
    const t = label.trim();
    if (!t) return _m;
    if (/^".*"$/.test(t)) return `${id}["${t.slice(1, -1).replace(/"/g, "'")}"]`;
    // Do not modify special shapes already handled or special syntax
    if (/^\(.*\)$/.test(t) || /^[\[\/\\]/.test(t)) return _m;
    return `${id}["${t.replace(/"/g, "'")}"]`;
  });

  // 7. Subgraph definitions:
  clean = clean.replace(/^(\s*subgraph\s+)(.*)$/gm, (_m, prefix: string, rest: string) => {
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

  // 8. Count subgraph vs end and append missing end statements
  const lines = clean.split('\n');
  let openCount = 0;
  let closeCount = 0;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith('%%')) continue;
    if (/^subgraph\b/i.test(line)) {
      openCount++;
    } else if (/^(?:loop|rect|opt|alt|par|critical|break)\b/i.test(line)) {
      openCount++;
    }
    if (/^end(?:\s+.*|\s*)$/i.test(line)) {
      closeCount++;
    }
  }

  if (openCount > closeCount) {
    const missing = openCount - closeCount;
    for (let i = 0; i < missing; i++) {
      clean += '\nend';
    }
  }

  // 9. Strip dangerous script/iframe tags
  clean = clean.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
  clean = clean.replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, '');

  return clean.trim();
}