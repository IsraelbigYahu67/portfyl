// A small Markdown reader for the legal texts in docs/legal/ (the public
// /terms and /privacy pages). It understands only what those files use:
// headings, paragraphs, "- " lists, pipe tables, block quotes, **bold**,
// *italic*, `code`, [links](url) and a trailing "\" hard line break. A code
// span holding a [[...]] marker becomes a "pending" node, so an unfinished
// placeholder is shown as pending instead of as raw syntax.

// The four legal files link to each other by file name; on the site those
// become the public routes. Any other relative link points into the repo and
// is rendered as plain text.
const DOC_ROUTES = {
  "terms-of-service-en.md": "/terms?lang=en",
  "podminky-uzivani-cs.md": "/terms?lang=cs",
  "privacy-policy-en.md": "/privacy?lang=en",
  "zasady-ochrany-osobnich-udaju-cs.md": "/privacy?lang=cs",
};

const INLINE = /`([^`]+)`|\*\*(.+?)\*\*|\*([^*\s][^*]*)\*|\[([^\]]+)\]\(([^)\s]+)\)/;
const EXTERNAL = /^https?:\/\//;

export function resolveLegalHref(href) {
  if (EXTERNAL.test(href) || href.startsWith("mailto:")) return href;
  return DOC_ROUTES[href] ?? null;
}

export function parseInline(text) {
  const nodes = [];
  let rest = text;
  while (rest) {
    const match = INLINE.exec(rest);
    if (!match) { nodes.push({ type: "text", value: rest }); break; }
    if (match.index) nodes.push({ type: "text", value: rest.slice(0, match.index) });
    const [whole, code, strong, em, linkText, href] = match;
    if (code !== undefined) {
      if (code.startsWith("[[") && code.endsWith("]]")) nodes.push({ type: "pending", value: code.slice(2, -2).trim() });
      else if (EXTERNAL.test(code)) nodes.push({ type: "link", href: code, children: [{ type: "text", value: code }] });
      else nodes.push({ type: "code", value: code });
    } else if (strong !== undefined) {
      nodes.push({ type: "strong", children: parseInline(strong) });
    } else if (em !== undefined) {
      nodes.push({ type: "em", children: parseInline(em) });
    } else {
      const target = resolveLegalHref(href);
      const children = parseInline(linkText);
      nodes.push(target ? { type: "link", href: target, children } : { type: "span", children });
    }
    rest = rest.slice(match.index + whole.length);
  }
  return nodes;
}

// Joins wrapped source lines into one inline run before parsing, because a
// code span or bold text may wrap across lines. A line ending in "\" keeps
// its break (CommonMark hard break), e.g. address blocks and the model form.
const HARD_BREAK = "\u0000";

function inlineLines(lines) {
  const text = lines
    .map((line, index) => (line.endsWith("\\") && index < lines.length - 1 ? `${line.slice(0, -1).trimEnd()}${HARD_BREAK}` : `${line} `))
    .join("")
    .replace(/\\$/, "")
    .trim();
  return restoreBreaks(parseInline(text));
}

function restoreBreaks(nodes) {
  return nodes.flatMap((node) => {
    if (node.children) return [{ ...node, children: restoreBreaks(node.children) }];
    if (node.type !== "text") return node.value ? [{ ...node, value: node.value.replaceAll(HARD_BREAK, " ") }] : [node];
    return node.value.split(HARD_BREAK).flatMap((part, index) => [
      ...(index ? [{ type: "break" }] : []),
      ...(part ? [{ type: "text", value: part }] : []),
    ]);
  });
}

const splitRow = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => parseInline(cell.trim()));
const isTableRule = (line) => /^\|?\s*:?-{3,}/.test(line.trim());
const startsTable = (lines, i) => lines[i].trim().startsWith("|") && isTableRule(lines[i + 1] ?? "");

export function slugifyHeading(text, index) {
  const ascii = text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const slug = ascii.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return slug || `section-${index + 1}`;
}

export function parseLegalMarkdown(source) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i += 1; continue; }

    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const text = heading[2].trim();
      blocks.push({ type: "heading", level: heading[1].length, text, children: parseInline(text) });
      i += 1;
      continue;
    }

    if (line.startsWith(">")) {
      const quoted = [];
      while (i < lines.length && lines[i].startsWith(">")) quoted.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push({ type: "quote", children: inlineLines(quoted) });
      continue;
    }

    if (startsTable(lines, i)) {
      const header = splitRow(line);
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(splitRow(lines[i++]));
      blocks.push({ type: "table", header, rows });
      continue;
    }

    if (/^\s*- /.test(line)) {
      const items = [];
      while (i < lines.length && lines[i].trim()) {
        if (/^\s*- /.test(lines[i])) items.push([lines[i].replace(/^\s*- /, "")]);
        else items[items.length - 1].push(lines[i].trim());
        i += 1;
      }
      blocks.push({ type: "list", items: items.map(inlineLines) });
      continue;
    }

    const paragraph = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|>|\s*- )/.test(lines[i]) && !startsTable(lines, i)) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: "paragraph", children: inlineLines(paragraph) });
  }
  return blocks;
}

// The page shows its own title and draft notice, so the document's H1 and
// the internal "DRAFT - DO NOT PUBLISH" quote right under it (which links
// into the repo) are lifted out of the body.
export function splitLegalDocument(source) {
  const blocks = parseLegalMarkdown(source);
  const titleIndex = blocks.findIndex((block) => block.type === "heading" && block.level === 1);
  const title = titleIndex >= 0 ? blocks[titleIndex].text : "";
  const body = blocks.filter((block, index) => index !== titleIndex && !(block.type === "quote" && index === titleIndex + 1));
  const used = new Set();
  const sections = [];
  body.forEach((block) => {
    if (block.type !== "heading" || block.level !== 2) return;
    let id = slugifyHeading(block.text, sections.length);
    while (used.has(id)) id = `${id}-${sections.length + 1}`;
    used.add(id);
    block.id = id;
    sections.push({ id, text: block.text.replace(/\*\*|`/g, "") });
  });
  return { title, blocks: body, sections, pendingCount: countPending(body) };
}

function countPending(nodes) {
  return nodes.reduce((total, node) => {
    if (node.type === "pending") return total + 1;
    const nested = [node.children, ...(node.items || []), node.header, ...(node.rows || [])]
      .filter(Boolean)
      .flatMap((group) => (Array.isArray(group[0]) ? group.flat() : group));
    return total + countPending(nested);
  }, 0);
}
