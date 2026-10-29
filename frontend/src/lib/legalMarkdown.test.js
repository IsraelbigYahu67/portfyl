import { parseInline, parseLegalMarkdown, splitLegalDocument } from "./legalMarkdown";

describe("parseInline", () => {
  it("turns [[...]] code spans into pending nodes and keeps other code", () => {
    expect(parseInline("Date: `[[TODO: publication date]]` at `portfyl.com`")).toEqual([
      { type: "text", value: "Date: " },
      { type: "pending", value: "TODO: publication date" },
      { type: "text", value: " at " },
      { type: "code", value: "portfyl.com" },
    ]);
  });

  it("maps sibling legal files to public routes and drops repo-internal links", () => {
    const [toPrivacy] = parseInline("[Privacy Policy](privacy-policy-en.md)");
    expect(toPrivacy).toMatchObject({ type: "link", href: "/privacy?lang=en" });
    const [internal] = parseInline("[notes](poznamky-pro-pravnika.md)");
    expect(internal).toEqual({ type: "span", children: [{ type: "text", value: "notes" }] });
  });

  it("links bare URLs in code spans and nests bold and italic", () => {
    expect(parseInline("`https://uoou.gov.cz`")[0]).toMatchObject({ type: "link", href: "https://uoou.gov.cz" });
    expect(parseInline("„**Služba**“ *(note)*")).toEqual([
      { type: "text", value: "„" },
      { type: "strong", children: [{ type: "text", value: "Služba" }] },
      { type: "text", value: "“ " },
      { type: "em", children: [{ type: "text", value: "(note)" }] },
    ]);
  });
});

describe("parseLegalMarkdown", () => {
  it("reads headings, wrapped paragraphs, hard breaks, lists and tables", () => {
    const blocks = parseLegalMarkdown([
      "## 1. Who", "", "Line one wraps", "onto two.", "", "Name: x \\", "Date: y", "",
      "- first", "  continued", "- second", "",
      "| A | B |", "|---|---|", "| **a** | `[[TODO]]` |",
    ].join("\r\n"));
    expect(blocks.map((block) => block.type)).toEqual(["heading", "paragraph", "paragraph", "list", "table"]);
    expect(blocks[1].children).toEqual([{ type: "text", value: "Line one wraps onto two." }]);
    expect(blocks[2].children).toEqual([{ type: "text", value: "Name: x" }, { type: "break" }, { type: "text", value: "Date: y" }]);
    expect(blocks[3].items[0]).toEqual([{ type: "text", value: "first continued" }]);
    expect(blocks[4].rows[0][1]).toEqual([{ type: "pending", value: "TODO" }]);
  });

  it("parses code spans and bold text that wrap across source lines", () => {
    const [paragraph] = parseLegalMarkdown("Seller `[[TODO: exact name\nof the entity]]` and **bold\ntext**.");
    expect(paragraph.children).toEqual([
      { type: "text", value: "Seller " },
      { type: "pending", value: "TODO: exact name of the entity" },
      { type: "text", value: " and " },
      { type: "strong", children: [{ type: "text", value: "bold text" }] },
      { type: "text", value: "." },
    ]);
  });
});

describe("splitLegalDocument", () => {
  it("lifts the title and the internal draft quote out and indexes sections", () => {
    const doc = splitLegalDocument("# Title\n\n> **DRAFT** see [x](../compliance/a.md)\n\nIntro `[[TODO: a]]`\n\n## 1. Kdo službu provozuje\n\nText\n");
    expect(doc.title).toBe("Title");
    expect(doc.blocks.some((block) => block.type === "quote")).toBe(false);
    expect(doc.sections).toEqual([{ id: "1-kdo-sluzbu-provozuje", text: "1. Kdo službu provozuje" }]);
    expect(doc.pendingCount).toBe(1);
  });
});
