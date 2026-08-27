import * as path from "node:path";
import { extensionModuleCapability } from "@oh-my-pi/pi-coding-agent/capability/extension-module";
import { loadCapability, type ExtensionModule } from "@oh-my-pi/pi-coding-agent/discovery";

const cwd = process.argv[2];
if (cwd === undefined || !path.isAbsolute(cwd)) {
	process.stderr.write("Usage: bun run scripts/discover-installed.ts <absolute-project-path>\n");
	process.exit(2);
}

const result = await loadCapability<ExtensionModule>(extensionModuleCapability.id, {
	cwd,
	providers: ["native"],
});

process.stdout.write(
	JSON.stringify({
		items: result.items.map(item => ({
			level: item.level,
			name: item.name,
			path: item.path,
		})),
		providers: result.providers,
		warnings: result.warnings,
	}),
);
