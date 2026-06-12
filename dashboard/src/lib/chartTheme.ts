import type { Decision, FlagTarget, Platform, Severity } from "@/types/slopgate";

// Decision → HSL color string
export const DECISION_COLORS: Record<Decision, string> = {
	allow: "hsl(142, 50%, 45%)",
	deny: "hsl(0, 72%, 51%)",
	block: "hsl(0, 85%, 60%)",
	ask: "hsl(38, 92%, 50%)",
	warn: "hsl(217, 91%, 60%)",
	context: "hsl(217, 70%, 50%)",
	info: "hsl(210, 20%, 55%)",
};

// Decision → Tailwind class pairs for badges
export const DECISION_BADGE_STYLE: Record<Decision, string> = {
	allow: "bg-signal-allow/20 text-signal-allow border-signal-allow/30",
	deny: "bg-signal-deny/20 text-signal-deny border-signal-deny/30",
	block: "bg-signal-block/20 text-signal-block border-signal-block/30",
	ask: "bg-signal-ask/20 text-signal-ask border-signal-ask/30",
	warn: "bg-signal-warn/20 text-signal-warn border-signal-warn/30",
	context: "bg-signal-context/20 text-signal-context border-signal-context/30",
	info: "bg-muted/20 text-muted-foreground border-muted/30",
};

// Decision → Tailwind dot class for timelines
export const DECISION_DOT_STYLE: Record<Decision, string> = {
	allow: "bg-signal-allow",
	deny: "bg-signal-deny",
	block: "bg-signal-block",
	ask: "bg-signal-ask",
	warn: "bg-signal-warn",
	context: "bg-signal-context",
	info: "bg-muted-foreground",
};

// Severity → HSL color string
export const SEVERITY_COLORS: Record<Severity, string> = {
	LOW: "hsl(210, 20%, 55%)",
	MEDIUM: "hsl(38, 92%, 50%)",
	HIGH: "hsl(20, 90%, 55%)",
	CRITICAL: "hsl(0, 85%, 60%)",
};

// Severity → Tailwind class
export const SEVERITY_TEXT_STYLE: Record<Severity, string> = {
	LOW: "text-severity-low",
	MEDIUM: "text-severity-medium",
	HIGH: "text-severity-high",
	CRITICAL: "text-severity-critical",
};

// Platform → Tailwind badge style
export const PLATFORM_BADGE_STYLE: Record<Platform, string> = {
	claude: "bg-platform-claude/20 text-platform-claude",
	codex: "bg-platform-codex/20 text-platform-codex",
	opencode: "bg-platform-opencode/20 text-platform-opencode",
	cursor: "bg-platform-cursor/20 text-platform-cursor",
	unknown: "bg-platform-unknown/20 text-platform-unknown",
};

// Flag target labels & colors (shared between FlagButton and FlaggedItemsPanel)
export const FLAG_TARGET_LABELS: Record<
	FlagTarget,
	{ label: string; color: string }
> = {
	openclaw: { label: "OpenClaw", color: "text-platform-opencode" },
	claude: { label: "Claude", color: "text-platform-claude" },
	codex: { label: "Codex", color: "text-platform-codex" },
};
