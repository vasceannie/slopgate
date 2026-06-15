import {
	AlertTriangle,
	ArrowUpDown,
	CheckCircle2,
	CircleDashed,
	Flame,
	FolderX,
	MapPin,
	PlugZap,
	RadioTower,
	RotateCcw,
	ShieldCheck,
	XCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import type { HarnessStatusState } from "@/hooks/useHarnessStatus";
import { cn } from "@/lib/utils";
import type {
	HarnessPlatformStatus,
	HarnessStatusResponse,
	OperationalContext,
	RuntimeConfig,
	Severity,
} from "@/types/slopgate";

const SEVERITY_COLOR: Record<Severity, string> = {
	LOW: "text-severity-low font-semibold",
	MEDIUM: "text-severity-medium font-semibold",
	HIGH: "text-severity-high font-semibold",
	CRITICAL: "text-severity-critical font-semibold",
};

const STATUS_CLASS: Record<HarnessPlatformStatus["status"], string> = {
	installed: "text-signal-allow bg-signal-allow/10 border-signal-allow/20 font-semibold",
	partial: "text-signal-ask bg-signal-ask/10 border-signal-ask/20 font-semibold",
	missing: "text-muted-foreground bg-muted/20 border-border font-medium",
	disabled: "text-muted-foreground bg-muted/20 border-border font-medium",
	error: "text-signal-deny bg-signal-deny/10 border-signal-deny/20 font-semibold",
};

const COUNT_BAR_MAX_WIDTH_PERCENT = 100;
const HIGHEST_HOOK_VOLUME_LIMIT = 6;
const MINIMUM_SCALE_DENOMINATOR = 1;

function StatusIcon({ status }: { status: HarnessPlatformStatus["status"] }) {
	if (status === "installed") return <CheckCircle2 className="w-3.5 h-3.5" />;
	if (status === "partial" || status === "error")
		return <AlertTriangle className="w-3.5 h-3.5" />;
	return <CircleDashed className="w-3.5 h-3.5" />;
}

function compactList(values: string[], limit = 3): string {
	if (values.length === 0) return "none";
	const head = values.slice(0, limit).join(", ");
	return values.length > limit ? `${head}, +${values.length - limit}` : head;
}

interface OpenCodeLiveConfigStatus {
	url: string;
	reachable: boolean;
	plugin_registered: boolean;
	error?: string | null;
}

type HarnessPlatformStatusWithLiveConfig = HarnessPlatformStatus & {
	live_config?: OpenCodeLiveConfigStatus;
};

function harnessPlatforms(
	status: HarnessStatusResponse | null,
): HarnessPlatformStatusWithLiveConfig[] {
	return (status?.platforms ?? []) as HarnessPlatformStatusWithLiveConfig[];
}

interface Props {
	config: RuntimeConfig;
	harnessStatus: HarnessStatusState;
	hottestRepos: Array<{ repo: string; count: number }>;
	operationalContext: OperationalContext;
}

function CountList({
	rows,
	emptyLabel = "No data",
}: {
	rows: Array<{ label: string; count: number }>;
	emptyLabel?: string;
}) {
	if (rows.length === 0) {
		return (
			<div className="text-xs text-muted-foreground px-2 py-1 italic">
				{emptyLabel}
			</div>
		);
	}
	const max = Math.max(
		...rows.map((r) => r.count),
		MINIMUM_SCALE_DENOMINATOR,
	);
	return (
		<div className="space-y-1.5">
			{rows.map((row, i) => {
				const percentage = Math.min(
					COUNT_BAR_MAX_WIDTH_PERCENT,
					Math.max(0, (row.count / max) * COUNT_BAR_MAX_WIDTH_PERCENT),
				);
				const wPct = `${percentage}%`;

				return (
					<div
						key={row.label}
						className="flex items-center justify-between gap-3 px-2 py-1.5 rounded-sm bg-muted/20 text-xs"
					>
						<span className="font-mono break-all text-foreground/90 font-medium" title={row.label}>
							{row.label}
						</span>
						<div className="flex items-center gap-3 shrink-0">
							<div className="w-14 h-1.5 rounded-full bg-muted/40 overflow-hidden">
								<div
									className={cn(
										"h-full rounded-full",
										i === 0 ? "bg-primary" : "bg-muted-foreground/50",
									)}
									style={{width:wPct}}
								/>
							</div>
							<span className="text-muted-foreground w-8 text-right font-mono font-semibold">
								{row.count}
							</span>
						</div>
					</div>
				);
			})}
		</div>
	);
}

function OpsCard({
	title,
	icon: Icon,
	children,
}: {
	title: string;
	icon: typeof ShieldCheck;
	children: ReactNode;
}) {
	return (
		<div className="border border-border rounded-md bg-card/30 p-4 shadow-sm">
			<div className="flex items-center gap-2 mb-3 pb-2 border-b border-border/50">
				<Icon className="w-4 h-4 text-primary" />
				<h4 className="text-xs font-bold text-foreground uppercase tracking-wider">
					{title}
				</h4>
			</div>
			{children}
		</div>
	);
}

function HarnessStatusPanel({
	harnessStatus,
}: {
	harnessStatus: HarnessStatusState;
}) {
	const { status, loading, error } = harnessStatus;
	const platforms = harnessPlatforms(status);

	return (
		<div className="space-y-2">
			<div className="flex items-center justify-between px-1">
				<h3 className="text-xs text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
					<PlugZap className="w-3.5 h-3.5" />
					Harness Status
				</h3>
				<div className="text-xs text-muted-foreground font-mono">
					read-only{status?.ssh_host ? ` · ${status.ssh_host}` : ""}
				</div>
			</div>

			<div className="border border-border rounded-md bg-card/30 p-4 space-y-4 divide-y divide-border/60">
				{loading && (
					<div className="text-xs text-muted-foreground">
						Checking installed hook harnesses…
					</div>
				)}
				{error && (
					<div className="flex items-center gap-2 text-xs text-signal-deny bg-signal-deny/10 border border-signal-deny/20 rounded-md px-3 py-2">
						<AlertTriangle className="w-4 h-4" />
						{error}
					</div>
				)}
				{!loading && !error && platforms.length === 0 && (
					<div className="text-xs text-muted-foreground">
						No harness status returned.
					</div>
				)}
				{platforms.map((platform, idx) => (
					<div
						key={platform.id}
						className={cn("space-y-3", idx > 0 && "pt-4")}
					>
						<div className="flex items-start justify-between gap-3">
							<div>
								<div className="flex items-center gap-2 flex-wrap">
									<span className="text-xs font-semibold text-foreground">{platform.label}</span>
									<span className="text-[10px] text-muted-foreground font-mono bg-muted/40 px-1.5 py-0.5 rounded">
										{platform.capability}
									</span>
								</div>
								<div className="text-xs text-muted-foreground/80 mt-1">
									{platform.support}
								</div>
							</div>
							<span
								className={cn(
									"shrink-0 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase font-semibold",
									STATUS_CLASS[platform.status],
								)}
							>
								<StatusIcon status={platform.status} />
								{platform.status}
							</span>
						</div>

						<div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2.5 text-xs text-muted-foreground">
							<div>
								<span className="uppercase tracking-wider font-semibold text-muted-foreground/75 text-[10px]">config path</span>
								<div
									className="font-mono text-foreground break-all mt-0.5 font-medium"
									title={platform.config_path}
								>
									{platform.config_path}
								</div>
							</div>
							<div>
								<span className="uppercase tracking-wider font-semibold text-muted-foreground/75 text-[10px]">
									dry-run install
								</span>
								<div
									className={cn(
										"font-mono mt-0.5 font-semibold",
										platform.dry_run.ok
											? "text-signal-allow"
											: "text-signal-ask",
									)}
								>
									{platform.dry_run.available
										? platform.dry_run.ok
											? "ok"
											: (platform.dry_run.note ??
												`exit ${platform.dry_run.returncode ?? "?"}`)
										: "unavailable"}
								</div>
							</div>
							<div>
								<span className="uppercase tracking-wider font-semibold text-muted-foreground/75 text-[10px]">events</span>
								<div className="font-mono text-foreground mt-0.5 font-medium">
									{platform.configured_events.length}/
									{platform.expected_events.length} configured
								</div>
							</div>
							<div>
								<span className="uppercase tracking-wider font-semibold text-muted-foreground/75 text-[10px]">commands</span>
								<div
									className={cn(
										"font-mono mt-0.5 font-semibold",
										platform.all_commands_reference_slopgate
											? "text-signal-allow"
											: "text-signal-ask",
									)}
								>
									{platform.slopgate_command_count} handle commands
								</div>
							</div>
						</div>

						{platform.feature_flag_path && (
							<div className="text-xs text-muted-foreground bg-muted/20 px-2.5 py-1.5 rounded">
								feature flag{" "}
								<span className="font-mono font-medium text-foreground">{platform.feature_flag_path}</span>:{" "}
								<span className="font-semibold text-foreground">
									{platform.feature_flag_enabled ? "enabled" : "missing/off"}
								</span>
							</div>
						)}
						{platform.missing_events.length > 0 && (
							<div className="rounded-sm border border-signal-ask/20 bg-signal-ask/10 px-2 py-1 text-xs text-signal-ask font-medium">
								missing events: {compactList(platform.missing_events)}
							</div>
						)}
						{platform.disabled_plugin_present && !platform.config_exists && (
							<div className="text-xs text-signal-ask bg-signal-ask/10 border border-signal-ask/20 rounded px-2 py-1">
								disabled plugin copy exists outside the auto-loaded plugin directory.
							</div>
						)}
						{platform.id === "opencode" && platform.live_config && (
							<div className="text-xs text-muted-foreground bg-muted/20 px-2.5 py-1.5 rounded space-y-1">
								<div className="flex items-center gap-1.5 flex-wrap">
									<span>live config URL:</span>
									<span className="font-mono font-medium text-foreground break-all">{platform.live_config.url}</span>
								</div>
								<div className="flex items-center gap-3 flex-wrap">
									<div>
										status:{" "}
										<span
											className={cn(
												"font-semibold",
												platform.live_config.reachable
													? "text-signal-allow"
													: "text-signal-ask",
											)}
										>
											{platform.live_config.reachable ? "reachable" : "unreachable"}
										</span>
									</div>
									<div>
										plugin:{" "}
										<span className="font-semibold text-foreground">
											{platform.live_config.plugin_registered ? "registered" : "not registered"}
										</span>
									</div>
								</div>
								{platform.live_config.error && (
									<div className="text-signal-deny font-medium mt-1">
										error: {platform.live_config.error}
									</div>
								)}
							</div>
						)}
						{platform.error && (
							<div className="text-xs text-signal-deny bg-signal-deny/10 border border-signal-deny/20 rounded px-2 py-1 font-semibold">
								{platform.error}
							</div>
						)}
					</div>
				))}
			</div>
		</div>
	);
}

export function DriftTuning({
	config,
	harnessStatus,
	hottestRepos,
	operationalContext,
}: Props) {
	const highestHookVolumeRows = hottestRepos.slice(0, HIGHEST_HOOK_VOLUME_LIMIT);
	const highestHookVolumeMax = Math.max(
		...highestHookVolumeRows.map((r) => r.count),
		MINIMUM_SCALE_DENOMINATOR,
	);

	return (
		<div className="space-y-4">
			<h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">
				Local rule tuning
			</h3>

			{/* Unified Configuration & Override Card */}
			<div className="border border-border rounded-md bg-card/30 p-4 space-y-6 shadow-sm">
				<div className="flex items-center gap-2 pb-2 border-b border-border/50">
					<ArrowUpDown className="w-4 h-4 text-primary" />
					<h4 className="text-xs text-foreground uppercase tracking-wider font-bold">
						Local Rule Configuration
					</h4>
				</div>

				<div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
					{/* Disabled Rules */}
					<div>
						<div className="flex items-center gap-1.5 mb-2.5">
							<XCircle className="w-4 h-4 text-signal-deny" />
							<h5 className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
								Disabled Rules ({config.disabled_rules.length})
							</h5>
						</div>
						<div className="space-y-1">
							{config.disabled_rules.map((r) => (
								<div
									key={r.rule_id}
									className="flex items-center justify-between px-2.5 py-1.5 rounded-sm bg-muted/20 text-xs font-mono"
								>
									<span className="text-foreground font-semibold">{r.rule_id}</span>
									<span className="text-[10px] text-muted-foreground/80 font-medium">
										{r.disabled_date}
									</span>
								</div>
							))}
							{config.disabled_rules.length === 0 && (
								<div className="px-2 py-1.5 text-xs text-muted-foreground italic">
									No disabled rules
								</div>
							)}
						</div>
					</div>

					{/* Severity Overrides */}
					<div>
						<div className="flex items-center gap-1.5 mb-2.5">
							<ArrowUpDown className="w-4 h-4 text-signal-ask" />
							<h5 className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
								Severity Overrides ({config.severity_overrides.length})
							</h5>
						</div>
						<div className="space-y-1">
							{config.severity_overrides.map((o) => (
								<div
									key={o.rule_id}
									className="flex items-center justify-between px-2.5 py-1.5 rounded-sm bg-muted/20 text-xs font-mono"
								>
									<span className="break-all font-semibold mr-2" title={o.rule_id}>
										{o.rule_id}
									</span>
									<div className="flex items-center gap-1.5 shrink-0 text-[10px] bg-background/40 px-1.5 py-0.5 rounded">
										<span className={cn(SEVERITY_COLOR[o.original])}>
											{o.original}
										</span>
										<span className="text-muted-foreground">→</span>
										<span className={cn("font-bold", SEVERITY_COLOR[o.override])}>
											{o.override}
										</span>
									</div>
								</div>
							))}
							{config.severity_overrides.length === 0 && (
								<div className="px-2 py-1.5 text-xs text-muted-foreground italic">
									No severity overrides
								</div>
							)}
						</div>
					</div>
				</div>

				{/* Supporting Info: Skipped Repos & Hook Volume */}
				<div className="border-t border-border/50 pt-4 grid grid-cols-1 gap-6 sm:grid-cols-2">
					{/* Skipped Repositories */}
					<div>
						<div className="flex items-center gap-2 mb-2.5">
							<FolderX className="w-4 h-4 text-muted-foreground" />
							<h5 className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
								Skipped Repositories
							</h5>
						</div>
						<div className="space-y-1">
							{config.skip_repos.map((r) => (
								<div
									key={r}
									className="px-2.5 py-1.5 rounded-sm bg-muted/20 text-xs font-mono text-foreground font-semibold break-all"
								>
									{r}
								</div>
							))}
							{config.skip_repos.length === 0 && (
								<div className="px-2 py-1.5 text-xs text-muted-foreground italic">
									No skipped repositories
								</div>
							)}
							<div className="text-[10px] text-muted-foreground mt-2 px-1 font-mono">
								+ {config.skip_paths.length} skip paths configured
							</div>
						</div>
					</div>

					{/* Highest Hook Volume */}
					<div>
						<div className="flex items-center gap-2 mb-2.5">
							<Flame className="w-4 h-4 text-signal-ask" />
							<h5 className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
								Highest Hook Volume
							</h5>
						</div>
						<div className="space-y-1.5">
							{highestHookVolumeRows.map((r, i) => {
								const percentage = Math.min(
									COUNT_BAR_MAX_WIDTH_PERCENT,
									Math.max(0, (r.count / highestHookVolumeMax) * COUNT_BAR_MAX_WIDTH_PERCENT),
								);
								const percentageLabel = percentage.toFixed(0);
								const wPct = `${percentage}%`;

								return (
									<div
										key={r.repo}
										className="flex items-center justify-between px-2.5 py-1.5 rounded-sm bg-muted/20 text-xs"
									>
										<span className="font-mono text-foreground font-semibold break-all mr-2" title={r.repo}>
											{r.repo}
										</span>
										<div className="flex items-center gap-2 shrink-0">
											<div className="w-16 h-1 rounded-full bg-muted/30 overflow-hidden">
												<div
													className={cn(
														"h-full rounded-full",
														i === 0 ? "bg-signal-ask" : "bg-primary",
													)}
													style={{width:wPct}}
												/>
											</div>
											<span className="text-muted-foreground font-mono text-[10px] w-14 text-right">
												{percentageLabel}% ({r.count})
											</span>
										</div>
									</div>
								);
							})}
							{hottestRepos.length === 0 && (
								<div className="px-2 py-1 text-xs text-muted-foreground italic">
									No active repositories
								</div>
							)}
						</div>
					</div>
				</div>
			</div>

			<HarnessStatusPanel harnessStatus={harnessStatus} />

			{/* Operational Context Card */}
			<div className="space-y-2">
				<h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">
					Operational Context
				</h3>
				<div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<OpsCard title="Platform Capability" icon={RadioTower}>
						<CountList
							rows={operationalContext.platformCapabilities}
							emptyLabel="No platform metadata"
						/>
						{operationalContext.degradedReasons.length > 0 && (
							<div className="mt-3 pt-3 border-t border-border/50">
								<div className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold mb-2">
									Top degraded reasons
								</div>
								<CountList rows={operationalContext.degradedReasons} />
							</div>
						)}
					</OpsCard>

					<OpsCard title="Enforcement Modes" icon={ShieldCheck}>
						<CountList
							rows={operationalContext.enforcementModes}
							emptyLabel="No enforcement metadata"
						/>
					</OpsCard>

					<OpsCard title="Resolved Repo Roots" icon={MapPin}>
						<CountList
							rows={operationalContext.repoRoots}
							emptyLabel="No repo root metadata"
						/>
						{operationalContext.pathlessResults > 0 && (
							<div className="text-xs text-signal-ask mt-2 font-medium">
								{operationalContext.pathlessResults} result
								{operationalContext.pathlessResults === 1 ? "" : "s"} had no
								candidate paths in this window.
							</div>
						)}
					</OpsCard>

					<OpsCard title="Deny Recovery" icon={RotateCcw}>
						<div className="px-2 py-1.5 rounded-sm bg-muted/20 text-xs flex items-center justify-between font-mono">
							<span className="text-muted-foreground font-sans">Resolution Rate</span>
							<span className="font-bold text-foreground">
								{operationalContext.resolutionRate === null
									? "—"
									: `${operationalContext.resolutionRate.toFixed(1)}%`}
							</span>
						</div>
						<div className="text-xs text-muted-foreground mt-2 px-1">
							{operationalContext.resolvedBlockedSessions}/
							{operationalContext.blockedSessions} blocked sessions later
							produced allow/context/warn/info.
						</div>
						{operationalContext.repeatedDenials.length > 0 && (
							<div className="mt-3 pt-3 border-t border-border/50">
								<div className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold mb-2">
									Repeated deny loops
								</div>
								<CountList rows={operationalContext.repeatedDenials} />
							</div>
						)}
					</OpsCard>
				</div>
			</div>
		</div>
	);
}
