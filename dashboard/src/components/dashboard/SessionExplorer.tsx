import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import {
    memo,
    type ReactNode,
    useCallback,
    useEffect,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import {
    DECISION_BADGE_STYLE,
    PLATFORM_BADGE_STYLE,
    SEVERITY_TEXT_STYLE,
} from "@/lib/chartTheme";
import type { SessionData } from "@/lib/sessionHelpers";
import {
    primarySessionCause,
    sessionActivitySummary,
} from "@/lib/sessionHelpers";
import { cn } from "@/lib/utils";
import type { Decision, Platform } from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import { SessionOutcomeSummary } from "./SessionOutcomeSummary";
import { SessionTimeline } from "./SessionTimeline";
import {
    calculateScrollAdjustment,
    determineAnchor,
} from "./sessionExplorerAnchoring";

interface Props {
    sessions: SessionData[];
}

type DateRangeFilter = "all" | "1h" | "6h" | "24h" | "7d";

const DATE_RANGE_LABELS: Record<DateRangeFilter, string> = {
    all: "All time",
    "1h": "1h",
    "6h": "6h",
    "24h": "24h",
    "7d": "7d",
};

const DATE_RANGES: DateRangeFilter[] = ["all", "1h", "6h", "24h", "7d"];
const DATE_RANGE_MS: Record<Exclude<DateRangeFilter, "all">, number> = {
    "1h": 60 * 60 * 1000,
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
    "7d": 7 * 24 * 60 * 60 * 1000,
};

function toggleSetValue<T>(selected: Set<T>, value: T): Set<T> {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return next;
}

function latestSessionTimestamp(session: SessionData): number {
	let latest = 0;
	const inspectTimestamp = (timestamp: string | undefined) => {
		if (!timestamp) return;
		const parsed = Date.parse(timestamp);
		if (Number.isFinite(parsed) && parsed > latest) latest = parsed;
	};
	for (const event of session.events) inspectTimestamp(event.timestamp);
	for (const finding of session.findings) inspectTimestamp(finding.timestamp);
	for (const result of session.results) inspectTimestamp(result.timestamp);
	for (const run of session.subprocesses) inspectTimestamp(run.timestamp);
	return latest;
}

function uniqueEventCandidatePaths(events: SessionData["events"]): string[] {
	const paths: string[] = [];
	const seen = new Set<string>();
	for (const event of events) {
		for (const path of event.candidate_paths ?? []) {
			if (!path || seen.has(path)) continue;
			seen.add(path);
			paths.push(path);
		}
	}
	return paths;
}

function matchesDateRange(
    session: SessionData,
    dateRange: DateRangeFilter,
): boolean {
    if (dateRange === "all") return true;
    const latest = latestSessionTimestamp(session);
    return latest > 0 && Date.now() - latest <= DATE_RANGE_MS[dateRange];
}

function matchesSearchQuery(session: SessionData, query: string): boolean {
	if (!query.trim()) return true;
	const q = query.toLowerCase().trim();

	if (session.title?.toLowerCase().includes(q)) return true;

	// Session ID
	const sessionIds = [
		session.id,
		session.parentSessionId,
		session.rootSessionId,
		session.originSessionId,
		...(session.secondaryIds ?? []),
		session.nativeSessionIds?.opencode,
		session.nativeSessionIds?.codex,
		session.nativeSessionIds?.claude,
		...(session.rawSessionIds ?? []),
		...(session.childSessions ?? []).flatMap(identitySearchIds),
		...(session.mirrorSessions ?? []).flatMap(identitySearchIds),
	].filter((id): id is string => Boolean(id));
	if (sessionIds.some((id) => id.toLowerCase().includes(q))) return true;

	// Platform
	if ((session.platforms ?? [session.platform]).some((p) => p.includes(q))) {
		return true;
	}

    // Outcome
    if (session.finalOutcome.toLowerCase().includes(q)) return true;

    // Tool name
    if (session.tools.some((t) => t.toLowerCase().includes(q))) return true;

    // Rule ID
    const hasRuleId =
        session.findings.some((f) => f.rule_id?.toLowerCase().includes(q)) ||
        session.results.some((r) =>
            r.findings.some((f) => f.rule_id?.toLowerCase().includes(q)),
        );
    if (hasRuleId) return true;

    // Candidate paths
    const cause = primarySessionCause(session);
    const causePaths = cause.paths || [];
    const eventCandidatePaths = session.events.flatMap(
        (e) => e.candidate_paths ?? [],
    );
    const allPaths = [...new Set([...causePaths, ...eventCandidatePaths])];
    if (
        allPaths.some((p) => {
            const lowerP = p.toLowerCase();
            const basename = p.split("/").pop() || "";
            return lowerP.includes(q) || basename.toLowerCase().includes(q);
        })
    ) {
        return true;
    }

    // Command text
    const eventCommands = session.events
        .map((e) => e.command)
        .filter((c): c is string => !!c);
    const resultCommands = session.results
        .map((r) => r.command)
        .filter((c): c is string => !!c);
    const subprocessCommands = session.subprocesses
        .map((s) => s.command)
        .filter((c): c is string => !!c);
    const allCommands = [
        ...eventCommands,
        ...resultCommands,
        ...subprocessCommands,
    ];
    if (allCommands.some((c) => c.toLowerCase().includes(q))) return true;

    return false;
}

function identitySearchIds(session: SessionData): Array<string | null | undefined> {
	return [
		session.id,
		session.parentSessionId,
		session.rootSessionId,
		session.originSessionId,
		...(session.secondaryIds ?? []),
		session.nativeSessionIds?.opencode,
		session.nativeSessionIds?.codex,
		session.nativeSessionIds?.claude,
	];
}

function matchesSessionFilters(
    session: SessionData,
    selectedOutcomes: Set<Decision>,
    selectedPlatforms: Set<Platform>,
    selectedLanguages: Set<string>,
    dateRange: DateRangeFilter,
    searchQuery: string,
): boolean {
	return (
		(selectedOutcomes.size === 0 ||
			selectedOutcomes.has(session.finalOutcome)) &&
		(selectedPlatforms.size === 0 ||
			(session.platforms ?? [session.platform]).some((platform) =>
				selectedPlatforms.has(platform),
			)) &&
        (selectedLanguages.size === 0 ||
            session.languages.some((language) =>
                selectedLanguages.has(language),
            )) &&
        matchesDateRange(session, dateRange) &&
        matchesSearchQuery(session, searchQuery)
    );
}

function sessionFallbackLabel(sessionId: string): string {
	return `${sessionId.slice(0, 16)}…`;
}

function sessionDisplayName(session: SessionData): string {
	const title = session.title?.trim();
	return title || sessionFallbackLabel(session.id);
}

function sessionTitleText(session: SessionData): string {
	const title = session.title?.trim();
	return title ? `${title} (${session.id})` : session.id;
}

export function SessionExplorer({ sessions }: Props) {
    const [expanded, setExpanded] = useState<string | null>(null);
    const [copied, setCopied] = useState<string | null>(null);
    const [page, setPage] = useState(0);
    const [openFilterMenu, setOpenFilterMenu] = useState<string | null>(null);
    const [selectedOutcomes, setSelectedOutcomes] = useState<Set<Decision>>(
        () => new Set(),
    );
    const [selectedPlatforms, setSelectedPlatforms] = useState<Set<Platform>>(
        () => new Set(),
    );
    const [selectedLanguages, setSelectedLanguages] = useState<Set<string>>(
        () => new Set(),
    );
    const [dateRange, setDateRange] = useState<DateRangeFilter>("all");
    const [searchQuery, setSearchQuery] = useState("");
    const tableBodyRef = useRef<HTMLTableSectionElement>(null);
    const isUserActionRef = useRef(false);
    const anchorRef = useRef<{ id: string; top: number } | null>(null);
    const lastAnchorIdRef = useRef<string | null>(null);

    const [updatedSessionIds, setUpdatedSessionIds] = useState<Set<string>>(new Set());
    const prevSignaturesRef = useRef<Record<string, string>>({});

    useEffect(() => {
        const nextSignatures: Record<string, string> = {};
        const updatedIds = new Set<string>();
        const hasPrev = Object.keys(prevSignaturesRef.current).length > 0;

        for (const s of sessions) {
            const sig = [
                s.title ?? "",
                s.finalOutcome,
                s.duration,
                s.eventCount,
                s.tools.join(","),
                s.platforms?.join(",") ?? s.platform,
                s.findings.length,
                s.results.length,
                s.subprocesses.length
            ].join("|");
            
            nextSignatures[s.id] = sig;

            if (hasPrev) {
                const prevSig = prevSignaturesRef.current[s.id];
                if (prevSig === undefined || prevSig !== sig) {
                    updatedIds.add(s.id);
                }
            }
        }

        prevSignaturesRef.current = nextSignatures;

        if (updatedIds.size > 0) {
            setUpdatedSessionIds((prev) => {
                const next = new Set(prev);
                for (const id of updatedIds) {
                    next.add(id);
                }
                return next;
            });
            const timer = setTimeout(() => {
                setUpdatedSessionIds(new Set());
            }, 2000);
            return () => clearTimeout(timer);
        }
    }, [sessions]);

    // Determine the anchor before DOM updates.
    useLayoutEffect(() => {
        const tableBody = tableBodyRef.current;
        return () => {
            if (isUserActionRef.current) return;

            const anchor = determineAnchor({
                expanded,
                tableBody,
            });
            if (anchor) {
                anchorRef.current = anchor;
                lastAnchorIdRef.current = anchor.id;
            }
        };
	}, [expanded]);


    // Reset user action flag at the end of the render/commit phase
    useEffect(() => {
        if (isUserActionRef.current) {
            isUserActionRef.current = false;
        }
    });
    const perPage = 15;
    const outcomes = useMemo(
        () =>
            [
                ...new Set(sessions.map((session) => session.finalOutcome)),
            ].sort(),
        [sessions],
    );
	const platforms = useMemo(
		() =>
			[
				...new Set(
					sessions.flatMap((session) => session.platforms ?? [session.platform]),
				),
			].sort(),
		[sessions],
	);
    const languages = useMemo(
        () =>
            [
                ...new Set(sessions.flatMap((session) => session.languages)),
            ].sort(),
        [sessions],
    );
    const filteredSessions = useMemo(
        () =>
            sessions.filter((session) =>
                matchesSessionFilters(
                    session,
                    selectedOutcomes,
                    selectedPlatforms,
                    selectedLanguages,
                    dateRange,
                    searchQuery,
                ),
            ),
        [
            sessions,
            selectedOutcomes,
            selectedPlatforms,
            selectedLanguages,
            dateRange,
            searchQuery,
        ],
    );
    const paginated = filteredSessions.slice(
        page * perPage,
        (page + 1) * perPage,
    );

    // Handle page state anchoring
    useEffect(() => {
        if (isUserActionRef.current) {
            return;
        }

        if (lastAnchorIdRef.current) {
            const index = filteredSessions.findIndex((s) => s.id === lastAnchorIdRef.current);
            if (index !== -1) {
                const newPage = Math.floor(index / 15);
                if (newPage !== page) {
                    setPage(newPage);
                }
            }
        }
    }, [filteredSessions, page]);

    // Handle scroll position anchoring.
    useLayoutEffect(() => {
        if (isUserActionRef.current) {
            return;
        }

        if (anchorRef.current) {
            const { id, top: oldTop } = anchorRef.current;
            anchorRef.current = null; // Clear it

            const adj = calculateScrollAdjustment(
                id,
                oldTop,
                tableBodyRef.current,
                window.scrollY
            );
            if (adj !== 0) {
                window.scrollBy({ top: adj, behavior: "auto" });
            }
        }
	}, []);

    const copyId = useCallback((id: string) => {
        navigator.clipboard.writeText(id);
        setCopied(id);
        setTimeout(() => setCopied(null), 1500);
    }, []);

    const resetSessionPaging = useCallback(() => {
        setPage(0);
        setExpanded(null);
    }, []);

    return (
        <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 px-1">
                <h3 className="text-xs text-muted-foreground uppercase tracking-wider font-semibold">
                    Session & Tool Explorer
                </h3>
                <div className="relative w-full sm:w-72">
                    <input
                        type="text"
                        placeholder="Search sessions..."
                        value={searchQuery}
                        onChange={(e) => {
                            isUserActionRef.current = true;
setSearchQuery(e.target.value);
resetSessionPaging();
}}
                        className="w-full bg-background/50 border border-border rounded px-2.5 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
                    />
                </div>
            </div>
            <div className="border border-border rounded-md bg-card/30 overflow-hidden">
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-border bg-background/25 px-3 py-2 text-[10px]">
                    <FilterGroup label="Outcome">
                        <MultiSelectMenu
                            menuId="outcome"
                            openMenuId={openFilterMenu}
                            setOpenMenuId={setOpenFilterMenu}
                            options={outcomes}
                            selected={selectedOutcomes}
                            onToggle={(outcome) => {
                                isUserActionRef.current = true;
setSelectedOutcomes((current) =>
toggleSetValue(current, outcome),
);
resetSessionPaging();
}}
                        />
                    </FilterGroup>
                    <FilterGroup label="Platform">
                        <MultiSelectMenu
                            menuId="platform"
                            openMenuId={openFilterMenu}
                            setOpenMenuId={setOpenFilterMenu}
                            options={platforms}
                            selected={selectedPlatforms}
                            onToggle={(platform) => {
                                isUserActionRef.current = true;
setSelectedPlatforms((current) =>
toggleSetValue(current, platform),
);
resetSessionPaging();
}}
                        />
                    </FilterGroup>
                    <FilterGroup label="Range">
                        {DATE_RANGES.map((range) => (
                            <FilterChip
                                key={range}
                                active={dateRange === range}
                                onClick={() => {
                                    isUserActionRef.current = true;
setDateRange(range);
resetSessionPaging();
}}
                            >
                                {DATE_RANGE_LABELS[range]}
                            </FilterChip>
                        ))}
                    </FilterGroup>
                    <FilterGroup label="Language">
                        <MultiSelectMenu
                            menuId="language"
                            openMenuId={openFilterMenu}
                            setOpenMenuId={setOpenFilterMenu}
                            options={languages}
                            selected={selectedLanguages}
                            onToggle={(language) => {
                                isUserActionRef.current = true;
setSelectedLanguages((current) =>
toggleSetValue(current, language),
);
resetSessionPaging();
}}
                        />
                    </FilterGroup>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-xs table-fixed" style={{ tableLayout: "fixed" }}>
                        <colgroup>
                            <col style={{ width: "32px" }} />
                            <col style={{ width: "180px" }} />
                            <col style={{ width: "90px" }} />
                            <col style={{ width: "220px" }} />
                            <col style={{ width: "110px" }} />
                            <col style={{ width: "130px" }} />
                            <col style={{ width: "200px" }} />
                            <col style={{ width: "70px" }} />
                            <col style={{ width: "40px" }} />
                        </colgroup>
                        <thead>
                            <tr className="border-b border-border text-muted-foreground select-none">
                                <th className="px-3 py-2 text-left" />
                                <th className="px-3 py-2 text-left">Session</th>
                                <th className="px-3 py-2 text-center">Outcome</th>
                                <th className="px-3 py-2 text-left">Primary cause</th>
                                <th className="px-3 py-2 text-left">Platform</th>
                                <th className="px-3 py-2 text-left">Agent activity</th>
                                <th className="px-3 py-2 text-left">Files / paths</th>
                                <th className="px-3 py-2 text-right">Duration</th>
                                <th className="px-3 py-2" />
                            </tr>
                        </thead>
                        <tbody ref={tableBodyRef}>
					{paginated.map((s) => (
						<SessionRow
							key={s.id}
							session={s}
isExpanded={expanded === s.id}
                                    isCopied={copied === s.id}
                                    isUpdated={updatedSessionIds.has(s.id)}
                                    onToggle={() => {
                                        isUserActionRef.current = true;
setExpanded(
expanded === s.id ? null : s.id,
                                        );
                                    }}
							onCopy={() => copyId(s.id)}
						/>
						))}
                            {paginated.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={9}
                                        className="px-3 py-6 text-center text-[10px] text-muted-foreground"
                                    >
                                        No sessions match the current filter.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
                <div className="flex items-center justify-between px-3 py-2 border-t border-border text-[10px] text-muted-foreground">
                    <span>
                        {filteredSessions.length} of {sessions.length} sessions
                    </span>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            disabled={page === 0}
                            onClick={() => {
                                isUserActionRef.current = true;
                                setPage((p) => p - 1);
                            }}
                            className="hover:text-foreground disabled:opacity-30 font-mono"
                        >
                            ← Prev
                        </button>
                        <span className="font-mono tabular-nums">
                            {page + 1}/
                            {Math.max(
                                1,
                                Math.ceil(filteredSessions.length / perPage),
                            )}
                        </span>
                        <button
                            type="button"
                            disabled={
                                (page + 1) * perPage >= filteredSessions.length
                            }
                            onClick={() => {
                                isUserActionRef.current = true;
                                setPage((p) => p + 1);
                            }}
                            className="hover:text-foreground disabled:opacity-30 font-mono"
                        >
                            Next →
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

const SessionRow = memo(function SessionRow({
    session: s,
    isExpanded,
    isCopied,
	isUpdated,
	onToggle,
	onCopy,
}: {
	session: SessionData;
	isExpanded: boolean;
	isCopied: boolean;
	isUpdated: boolean;
	onToggle: () => void;
	onCopy: () => void;
}) {
	const cause = useMemo(() => primarySessionCause(s), [s]);
	const activity = useMemo(() => sessionActivitySummary(s), [s]);

	const causePaths = cause.paths || [];
	const childSessions = s.childSessions ?? [];
	const mirrorSessions = s.mirrorSessions ?? [];
	const childSessionIds = new Set(childSessions.map((session) => session.id));
	const mirrorOnlySessions = mirrorSessions.filter(
		(session) => !childSessionIds.has(session.id),
	);
	const rawSessionIds = s.rawSessionIds ?? [s.id];
	const displayName = sessionDisplayName(s);
	const hasTitle = Boolean(s.title?.trim());
	const childMirrorCount = childSessions.filter(
		(session) => session.lineageRole === "child_mirror",
	).length;
	const childOnlyCount = childSessions.length - childMirrorCount;
	const mirrorOnlyCount = mirrorOnlySessions.length;
	const lineageCount = childSessions.length + mirrorOnlySessions.length;
	const genericPaths = useMemo(() => uniqueEventCandidatePaths(s.events), [s.events]);
	const displayPaths = causePaths.length > 0 ? causePaths : genericPaths;

    return (
        <>
            <tr
                className={cn(
                    "border-b border-border/50 hover:bg-muted/20 cursor-pointer transition-all duration-150 h-[40px] align-middle",
                    isExpanded && "bg-muted/10",
                    isUpdated && "session-row-updated"
                )}
                onClick={onToggle}
                data-session-id={s.id}
            >
                <td className="px-3 py-2 align-middle whitespace-nowrap overflow-hidden">
                    <button
                        type="button"
                        onClick={(e) => {
                            e.stopPropagation();
                            onToggle();
                        }}
                        aria-expanded={isExpanded}
                        aria-label={isExpanded ? "Collapse session" : "Expand session"}
                        className="flex items-center justify-center p-1 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus:ring-1 focus:ring-primary"
                    >
                        {isExpanded ? (
                            <ChevronDown className="w-3.5 h-3.5" />
                        ) : (
                            <ChevronRight className="w-3.5 h-3.5" />
                        )}
                    </button>
                </td>
				<td className="px-3 py-2 font-mono align-middle whitespace-nowrap overflow-hidden">
					<span className="flex items-center gap-1 min-w-0" title={sessionTitleText(s)}>
						<span
							className={cn(
								"truncate",
								hasTitle ? "font-sans font-medium text-foreground" : "font-mono"
							)}
							style={{ maxWidth: "110px" }}
						>
							{displayName}
						</span>
						{lineageCount > 0 && (
							<span className="rounded border border-primary/30 bg-primary/10 px-1 py-0.5 text-[9px] font-sans uppercase text-primary">
								+{lineageCount} linked
							</span>
						)}
						<button
                            type="button"
                            onClick={(e) => {
                                e.stopPropagation();
                                onCopy();
                            }}
                            className="hover:text-primary shrink-0"
                        >
                            {isCopied ? (
                                <Check className="w-3 h-3" />
                            ) : (
                                <Copy className="w-3 h-3" />
                            )}
                        </button>
                    </span>
                </td>
                <td className="px-3 py-2 text-center align-middle whitespace-nowrap overflow-hidden">
                    <span
                        className={cn(
                            "inline-block px-1.5 py-0.5 rounded border text-[10px] uppercase font-bold text-center w-16 shrink-0",
                            DECISION_BADGE_STYLE[s.finalOutcome],
                        )}
                    >
                        {s.finalOutcome}
                    </span>
                </td>
                <td
                    className="px-3 py-2 align-middle truncate whitespace-nowrap overflow-hidden"
                    title={cause.message || ""}
                >
                    {cause.decision === "allow" ? (
                        <span className="text-signal-allow font-medium text-[10px] truncate block">
                            Clean allow
                        </span>
                    ) : (
                        <span className="flex items-center gap-1 text-[10px] truncate w-full">
                            {cause.severity && (
                                <span
                                    className={cn(
                                        "font-bold shrink-0",
                                        SEVERITY_TEXT_STYLE[cause.severity],
                                    )}
                                >
                                    [{cause.severity}]
                                </span>
                            )}
                            {cause.ruleId && (
                                <strong className="text-foreground shrink-0 truncate max-w-[100px]">
                                    {cause.ruleId}:{" "}
                                </strong>
                            )}
                            <span className="text-muted-foreground truncate min-w-0">
                                {cause.message}
                            </span>
                        </span>
                    )}
                </td>
				<td className="px-3 py-2 align-middle whitespace-nowrap overflow-hidden">
					<div className="flex items-center gap-1 select-none">
						{(() => {
							const allPlatforms = s.platforms ?? [s.platform];
							const firstPlatform = allPlatforms[0];
							const extraPlatformsCount = allPlatforms.length - 1;
							const fullListStr = allPlatforms.join(", ");
							return (
								<>
									{firstPlatform ? (
										<span
											className={cn(
												"px-1.5 py-0.5 rounded text-[10px] uppercase font-medium truncate inline-block text-center shrink-0",
												PLATFORM_BADGE_STYLE[firstPlatform],
											)}
											style={{ width: "64px" }}
											title={fullListStr}
										>
											{firstPlatform}
										</span>
									) : (
										<span className="text-muted-foreground text-[10px] italic shrink-0">None</span>
									)}
									{extraPlatformsCount > 0 ? (
										<span
											className="text-muted-foreground text-[10px] font-semibold tabular-nums shrink-0 w-6 text-right"
											title={fullListStr}
										>
											+{extraPlatformsCount}
										</span>
									) : (
										<span className="shrink-0 w-6" />
									)}
								</>
							);
						})()}
					</div>
				</td>
                <td className="px-3 py-2 align-middle whitespace-nowrap overflow-hidden">
                    <div className="flex items-center gap-1 select-none">
                        {activity.lastTool ? (
                            <span 
                                className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-medium text-foreground truncate inline-block text-center shrink-0 w-20"
                                title={activity.lastTool}
                            >
                                {activity.lastTool}
                            </span>
                        ) : (
                            <span className="text-muted-foreground text-[10px] italic inline-block w-20 text-center shrink-0">
                                None
                            </span>
                        )}
                        {activity.toolCount > 1 ? (
                            <span
                                className="text-muted-foreground text-[10px] font-semibold tabular-nums shrink-0 w-6 text-right"
                                title={`${activity.toolCount} tools used`}
                            >
                                +{activity.toolCount - 1}
                            </span>
                        ) : (
                            <span className="shrink-0 w-6" />
                        )}
                    </div>
                </td>
                <td className="px-3 py-2 align-middle whitespace-nowrap overflow-hidden">
                    <div className="flex items-center gap-1 select-none">
                        {(() => {
                            const firstPath = displayPaths[0];
                            const extraPathsCount = displayPaths.length - 1;
                            const fullPathsList = displayPaths.join("\n");
                            return (
                                <>
                                    {firstPath ? (
                                        <span
                                            className={cn(
                                                "px-1 py-0.5 bg-muted rounded text-[10px] font-mono truncate inline-block shrink-0 w-32 text-left",
                                                causePaths.includes(firstPath) &&
                                                    "border border-primary/20 bg-primary/5 text-primary",
                                            )}
                                            title={firstPath}
                                        >
                                            {firstPath.split("/").pop()}
                                        </span>
                                    ) : (
                                        <span className="text-muted-foreground text-[10px] italic inline-block w-32 shrink-0">
                                            None
                                        </span>
                                    )}
                                    {extraPathsCount > 0 ? (
										<span
											className="text-muted-foreground text-[10px] font-semibold tabular-nums shrink-0 w-6 text-right"
											title={fullPathsList}
										>
											+{extraPathsCount}
                                        </span>
									) : (
										<span className="shrink-0 w-6" />
									)}
                                </>
                            );
                        })()}
                    </div>
                </td>
                <td className="px-3 py-2 text-right text-muted-foreground align-middle whitespace-nowrap tabular-nums font-mono">
                    {s.duration > 60000
                        ? `${(s.duration / 60000).toFixed(1)}m`
                        : `${(s.duration / 1000).toFixed(0)}s`}
                </td>
                <td className="px-3 py-2 align-middle whitespace-nowrap overflow-hidden">
                    <FlagButton
                        itemType="session"
                        itemId={s.id}
                        label={`${displayName} (${s.platform}, ${s.finalOutcome})`}
                        compact
                    />
                </td>
            </tr>
			{isExpanded && (
				<tr>
					<td colSpan={9} className="p-0">
						<div className="max-h-[60vh] overflow-y-auto border-b border-border bg-background/10">
							{(lineageCount > 0 || (s.rawSessionIds ?? []).length > 1) && (
								<div className="border-b border-border bg-background/40 px-4 py-3 text-[10px] text-muted-foreground">
									<div className="flex flex-wrap items-center gap-2">
										<span className="font-semibold uppercase tracking-wide text-foreground">
											Lineage
										</span>
										<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
											{s.lineageConfidence ?? "none"}
										</span>
										{rawSessionIds.length > 1 && (
											<span className="rounded border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-primary">
												{rawSessionIds.length} grouped sessions
											</span>
										)}
										{childOnlyCount > 0 && (
											<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
												{childOnlyCount} child
											</span>
										)}
										{childMirrorCount > 0 && (
											<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
												{childMirrorCount} child + mirror
											</span>
										)}
										{mirrorOnlyCount > 0 && (
											<span className="rounded border border-border/40 bg-muted/20 px-1.5 py-0.5">
												{mirrorOnlyCount} mirror
											</span>
										)}
									</div>
								</div>
							)}
							<SessionOutcomeSummary session={s} />
							<SessionTimeline session={s} />
						</div>
					</td>
				</tr>
			)}
        </>
    );
})

function FilterGroup({
    label,
    children,
}: {
    label: string;
    children: ReactNode;
}) {
    return (
        <div className="flex flex-wrap items-center gap-1.5">
            <span className="min-w-14 text-muted-foreground">{label}:</span>
            {children}
        </div>
    );
}

function FilterChip({
    active,
    onClick,
    children,
}: {
    active: boolean;
    onClick: () => void;
    children: ReactNode;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "rounded border px-1.5 py-0.5 transition-colors",
                active
                    ? "border-primary/40 bg-primary/15 text-primary"
                    : "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
            )}
        >
            {children}
        </button>
    );
}

function MultiSelectMenu<T extends string>({
    menuId,
    openMenuId,
    setOpenMenuId,
    options,
    selected,
    onToggle,
}: {
    menuId: string;
    openMenuId: string | null;
    setOpenMenuId: (menuId: string | null) => void;
    options: T[];
    selected: Set<T>;
    onToggle: (option: T) => void;
}) {
    const isOpen = openMenuId === menuId;
    const selectionLabel =
        selected.size === 0 ? "All" : `${selected.size} selected`;
    const triggerRef = useRef<HTMLButtonElement>(null);

    useEffect(() => {
        if (!isOpen) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                setOpenMenuId(null);
                triggerRef.current?.focus();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, setOpenMenuId]);

    return (
        <div className="relative">
            <button
                type="button"
                ref={triggerRef}
                onClick={() => setOpenMenuId(isOpen ? null : menuId)}
                className={cn(
                    "rounded border px-1.5 py-0.5 transition-colors",
                    selected.size > 0 || isOpen
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
                )}
            >
                {selectionLabel}
            </button>
            {isOpen && (
                <div className="absolute left-0 top-full z-30 mt-1 min-w-40 rounded border border-border bg-popover p-2 shadow-lg">
                    <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">
                        Options
                    </div>
                    <div className="max-h-48 space-y-1 overflow-y-auto">
                        {options.map((option) => (
                            <label
                                key={option}
                                className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-muted-foreground hover:bg-muted/20 hover:text-foreground"
                            >
                                <input
                                    type="checkbox"
                                    checked={selected.has(option)}
                                    onChange={() => onToggle(option)}
                                    className="h-3 w-3 rounded border-border text-primary focus:ring-primary"
                                />
                                <span>{option}</span>
                            </label>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
