import { existsSync, readdirSync, readFileSync } from "node:fs";
import mermaid from "mermaid";

// Guards the backend/frontend contract: every golden diagram the backend produces (both formats,
// every depth) must be valid Mermaid for the pinned version.
const dir = "../backend/tests/golden";
const cases = existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".mmd")).sort() : [];

describe.skipIf(!existsSync(dir))("backend golden diagrams parse with the pinned mermaid", () => {
  test("there are goldens for both formats and every depth", () => {
    expect(cases).toEqual(
      expect.arrayContaining([
        "compose_monorepo_c4.mmd",
        "compose_monorepo_flowchart.mmd",
        "nested_c4_depth1.mmd",
        "nested_c4_depth3.mmd",
        "nested_flowchart_depth1.mmd",
        "nested_flowchart_depth3.mmd",
        "nested_layers_depth1.mmd",
        "nested_layers_depth3.mmd",
        "cyclic_layers_depth2.mmd",
      ]),
    );
  });

  test.each(cases)("%s", async (name) => {
    expect(await mermaid.parse(readFileSync(`${dir}/${name}`, "utf8"))).toBeTruthy();
  });

  test("queue and container symbols parse too", async () => {
    const text = readFileSync(`${dir}/compose_monorepo_c4.mmd`, "utf8")
      .replace("ContainerDb(redis", "ContainerQueue(redis")
      .replace("Container_Boundary(web", 'Container(web_x, "Web", "React")\n    Container_Boundary(web');
    expect(await mermaid.parse(text)).toBeTruthy();
  });
});
