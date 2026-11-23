import { existsSync, readFileSync } from "node:fs";

// The browser-tab icon: index.html must point at a real, valid SVG that ships with the build.
const html = readFileSync("index.html", "utf8");
const href = /<link rel="icon"[^>]*href="([^"]+)"/.exec(html)?.[1];

test("index.html declares an SVG icon", () => {
  expect(href).toBe("/favicon.svg");
  expect(html).toContain('type="image/svg+xml"');
});

test("the icon file exists in public/ and is a well-formed, self-contained SVG", () => {
  const file = `public${href}`;
  expect(existsSync(file)).toBe(true);
  const svg = readFileSync(file, "utf8");
  expect(svg).toMatch(/^<svg [^>]*xmlns="http:\/\/www\.w3\.org\/2000\/svg"/);
  expect(svg).toContain('viewBox="0 0 64 64"');
  expect(svg).not.toMatch(/<script|href="http|<image/); // no scripts or external resources
  expect(svg.match(/<svg/g)).toHaveLength(1);
  expect(svg.trimEnd().endsWith("</svg>")).toBe(true);
});
