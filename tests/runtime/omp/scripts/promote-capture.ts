import { mkdir, rm } from "node:fs/promises";
import * as path from "node:path";

import { assertCaptureDirectoriesEqual, CAPTURE_FILES } from "./envelope-capture.ts";

const fixtureRoot = path.resolve(import.meta.dir, "../../../fixtures/omp");
const captureRoot = path.join(fixtureRoot, ".capture");
const versionRoot = path.join(fixtureRoot, "18.0.5");

await rm(versionRoot, { recursive: true, force: true });
await mkdir(versionRoot, { recursive: true });
for (const filename of CAPTURE_FILES) {
	const source = Bun.file(path.join(captureRoot, filename));
	if (!(await source.exists())) throw new Error(`Missing captured envelope: ${filename}`);
	await Bun.write(path.join(versionRoot, filename), await source.arrayBuffer());
}
await assertCaptureDirectoriesEqual(captureRoot, versionRoot);
