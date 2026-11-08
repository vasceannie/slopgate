/**
 * Starts a fresh Pi ResourceLoader from its scoped settings and reports loaded
 * extension paths. This exercises native package sources and resource filters.
 */
import {
  DefaultResourceLoader,
  createEventBus,
} from "@earendil-works/pi-coding-agent";
import * as path from "node:path";

const [cwd, agentDir] = process.argv.slice(2);
if (!cwd || !path.isAbsolute(cwd) || !agentDir || !path.isAbsolute(agentDir)) {
  process.stderr.write("Usage: bun run scripts/discover-registered.ts <absolute-project> <absolute-agent-dir>\n");
  process.exit(2);
}

const loader = new DefaultResourceLoader({ cwd, agentDir, eventBus: createEventBus() });
await loader.reload({ resolveProjectTrust: async () => true });
const result = loader.getExtensions();
process.stdout.write(`${JSON.stringify({
  errors: result.errors,
  extensions: result.extensions.map(extension => extension.path),
})}\n`);
