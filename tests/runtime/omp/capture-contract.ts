import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

import { assertCaptureDirectoriesEqual, captureEnvelopes } from "./scripts/envelope-capture.ts";

const fixtureRoot = path.resolve(import.meta.dir, "../../fixtures/omp");
const captureRoot = path.join(fixtureRoot, ".capture");
const comparisonRoot = await mkdtemp(path.join(tmpdir(), "slopgate-omp-capture-compare-"));

try {
	await captureEnvelopes(captureRoot);
	await captureEnvelopes(comparisonRoot);
	await assertCaptureDirectoriesEqual(captureRoot, comparisonRoot);
} finally {
	await rm(comparisonRoot, { recursive: true, force: true });
}
