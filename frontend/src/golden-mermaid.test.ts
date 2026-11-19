import { existsSync, readFileSync } from "node:fs";
import mermaid from "mermaid";

// Guards the backend/frontend contract: text produced by the backend must be valid Mermaid.
const dir = "../backend/tests/golden";
const cases = ["compose_monorepo_c4.mmd", "compose_monorepo_flowchart.mmd"];

describe.skipIf(!existsSync(dir))("backend golden diagrams parse with the pinned mermaid", () => {
  test.each(cases)("%s", async (name) => {
    expect(await mermaid.parse(readFileSync(`${dir}/${name}`, "utf8"))).toBeTruthy();
  });

  test("queue and container symbols parse too", async () => {
    const text = readFileSync(`${dir}/compose_monorepo_c4.mmd`, "utf8")
      .replace("ContainerDb(redis", "ContainerQueue(redis")
      .replace("Container_Boundary(web", "Container(web_x, \"Web\", \"React\")\n    Container_Boundary(web");
    expect(await mermaid.parse(text)).toBeTruthy();
  });
});
