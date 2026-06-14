import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { Fragment, memo, useCallback, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SEVERITY_COLORS } from "@/lib/chartTheme";
import { cn } from "@/lib/utils";
import type { RuleMetadata } from "@/types/slopgate";
import { categorySortIndex, getCategory } from "./model";

type FilterType = "all" | "hot" | "disabled" | "partial" | "unsupported" | "changed";

interface RuleListProps {
	allRules: Array<RuleMetadata & { isChanged?: boolean }>;
	selectedRuleId: string | null;
	onSelectRule: (ruleId: string) => void;
}

const actionBadgeStyles: Record<string, string> = {
	deny: "bg-signal-block/20 text-signal-block border border-signal-block/30",
	block: "bg-signal-block/20 text-signal-block border border-signal-block/30",
	warn: "bg-signal-warn/20 text-signal-warn border border-signal-warn/30",
	ask: "bg-signal-ask/20 text-signal-ask border border-signal-ask/30",
	allow: "bg-signal-allow/20 text-signal-allow border border-signal-allow/30",
	context: "bg-muted text-muted-foreground border border-border",
	lint: "bg-primary/10 text-primary border border-primary/20",
};

interface StatusCellProps {
	supported: boolean;
	enabled: boolean;
	partiallyEnabled?: boolean;
	unsupportedReason?: string;
	activeColor?: string;
	title: string;
}

const StatusCell = memo(function StatusCell({
	supported,
	enabled,
	partiallyEnabled,
	unsupportedReason,
	activeColor = "bg-signal-allow",
	title,
}: StatusCellProps) {
	if (!supported) {
		return (
			<td className="px-2 py-2.5 text-left">
				<Badge
					variant="outline"
					className="text-[0.75rem] border-transparent bg-muted/40 text-muted-foreground/80 font-normal whitespace-nowrap px-1.5 py-0.5"
				>
					{unsupportedReason}
				</Badge>
			</td>
		);
	}

	return (
		<td className="px-2 py-2.5 text-left">
			<span
				className={cn(
					"inline-block w-2.5 h-2.5 rounded-full border border-black/10",
					partiallyEnabled
						? "bg-signal-ask"
						: enabled
							? activeColor
							: "bg-muted-foreground/30",
				)}
				title={title}
			/>
		</td>
	);
});

interface RuleIdentityCellProps {
	ruleId: string;
	title: string;
	description?: string;
	sevColor: string;
}

const RuleIdentityCell = memo(function RuleIdentityCell({
	ruleId,
	title,
	description,
	sevColor,
}: RuleIdentityCellProps) {
	return (
		<>
			<td
				className="px-3 py-2.5 font-mono text-[0.875rem] font-semibold truncate max-w-[200px]"
				style={{ color: sevColor }}
			>
				{ruleId}
			</td>
			<td className="px-3 py-2.5 max-w-xs md:max-w-md truncate">
				<div className="font-semibold text-foreground truncate">
					{title}
				</div>
				{description && (
					<div className="text-[0.75rem] text-muted-foreground truncate mt-0.5">
						{description}
					</div>
				)}
			</td>
		</>
	);
});

interface RuleRowProps {
	rule: RuleMetadata & { isChanged?: boolean };
	isSelected: boolean;
	onSelectRule: (ruleId: string) => void;
	sevColor: string;
}

const RuleRow = memo(function RuleRow({
	rule,
	isSelected,
	onSelectRule,
	sevColor,
}: RuleRowProps) {
	const handleSelect = useCallback(() => {
		onSelectRule(rule.rule_id);
	}, [rule.rule_id, onSelectRule]);

	return (
		<tr
			onClick={handleSelect}
			className={cn(
				"border-b border-border/30 cursor-pointer hover:bg-muted/25 active:bg-muted/30 transition-colors duration-150 ease-out-quint animate-in fade-in slide-in-from-top-1 duration-200",
				!rule.enabled && "opacity-60",
				isSelected && "bg-primary/10 hover:bg-primary/15",
			)}
		>
			<td className="px-3 py-2.5" />
			<StatusCell
				supported={rule.hookSupported}
				enabled={rule.hookEnabled}
				unsupportedReason={rule.hookUnsupportedReason}
				title={rule.hookEnabled ? "Hook active" : "Hook Off"}
			/>
			<StatusCell
				supported={rule.cliSupported}
				enabled={rule.cliEnabled}
				partiallyEnabled={rule.cliPartiallyEnabled}
				unsupportedReason={rule.cliUnsupportedReason}
				activeColor="bg-primary"
				title={
					rule.cliPartiallyEnabled
						? "CLI partially active"
						: rule.cliEnabled
							? "CLI active"
							: "CLI Off"
				}
			/>
			<RuleIdentityCell
				ruleId={rule.rule_id}
				title={rule.title}
				description={rule.description}
				sevColor={sevColor}
			/>
			<td className="px-3 py-2.5">
				<Badge
					variant="outline"
					className="text-[0.75rem] px-2 py-0.5 rounded font-medium uppercase border"
					style={{
						backgroundColor: `${sevColor}15`,
						color: sevColor,
						borderColor: `${sevColor}25`,
					}}
				>
					{rule.severity}
				</Badge>
			</td>
			<td className="px-3 py-2.5">
				<Badge
					variant="outline"
					className={cn(
						"text-[0.75rem] px-2 py-0.5 rounded uppercase font-medium border",
						actionBadgeStyles[rule.action],
					)}
				>
					{rule.action}
				</Badge>
			</td>
			<td className="px-3 py-2.5 text-right font-mono font-medium">
				{rule.fireCount > 0 ? (
					<span className="text-signal-ask font-semibold">
						{rule.fireCount}
					</span>
				) : (
					<span className="text-muted-foreground/30">—</span>
				)}
			</td>
			<td className="px-3 py-2.5 text-center">
				{rule.isChanged ? (
					<Badge
						variant="outline"
						className="inline-flex items-center px-1.5 py-0.5 bg-signal-ask/15 text-signal-ask rounded text-[0.75rem] font-semibold border border-signal-ask/25"
					>
						Changed
					</Badge>
				) : (
					<span className="text-muted-foreground/20 text-[0.75rem] font-medium">
						—
					</span>
				)}
			</td>
		</tr>
	);
}, (prev, next) => {
	return (
		prev.isSelected === next.isSelected &&
		prev.rule.rule_id === next.rule.rule_id &&
		prev.rule.title === next.rule.title &&
		prev.rule.description === next.rule.description &&
		prev.rule.severity === next.rule.severity &&
		prev.rule.action === next.rule.action &&
		prev.rule.fireCount === next.rule.fireCount &&
		prev.rule.hookEnabled === next.rule.hookEnabled &&
		prev.rule.cliEnabled === next.rule.cliEnabled &&
		prev.rule.cliPartiallyEnabled === next.rule.cliPartiallyEnabled &&
		prev.rule.hookSupported === next.rule.hookSupported &&
		prev.rule.cliSupported === next.rule.cliSupported &&
		prev.rule.hookUnsupportedReason === next.rule.hookUnsupportedReason &&
		prev.rule.cliUnsupportedReason === next.rule.cliUnsupportedReason &&
		prev.rule.isChanged === next.rule.isChanged
	);
});

interface FilterBarProps {
	search: string;
	onSearchChange: (val: string) => void;
	activeFilter: FilterType;
	onFilterChange: (filter: FilterType) => void;
	filterOptions: Array<{ value: FilterType; label: string }>;
}

const FilterBar = memo(function FilterBar({
	search,
	onSearchChange,
	activeFilter,
	onFilterChange,
	filterOptions,
}: FilterBarProps) {
	return (
		<div className="flex flex-col lg:flex-row gap-3 items-stretch lg:items-center justify-between">
			<div className="relative flex-1 max-w-xs">
				<Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
				<Input
					value={search}
					onChange={(e) => onSearchChange(e.target.value)}
					placeholder="Search rules..."
					className="pl-8 h-8 text-[0.875rem] bg-background"
				/>
			</div>
			<div className="flex flex-wrap gap-1">
				{filterOptions.map((opt) => (
					<Button
						type="button"
						key={opt.value}
						variant={activeFilter === opt.value ? "default" : "outline"}
						size="sm"
						onClick={() => onFilterChange(opt.value)}
						className="h-8 px-2.5 text-[0.875rem]"
					>
						{opt.label}
					</Button>
				))}
			</div>
		</div>
	);
});

interface CategoryHeaderRowProps {
	catLabel: string;
	emoji: string;
	rulesCount: number;
	activeCount: number;
	totalFires: number;
	isExpanded: boolean;
	onToggle: (label: string) => void;
}

const CategoryHeaderRow = memo(function CategoryHeaderRow({
	catLabel,
	emoji,
	rulesCount,
	activeCount,
	totalFires,
	isExpanded,
	onToggle,
}: CategoryHeaderRowProps) {
	const handleToggle = useCallback(() => {
		onToggle(catLabel);
	}, [catLabel, onToggle]);

	return (
		<tr
			className="border-b border-border bg-muted/40 cursor-pointer select-none hover:bg-muted/60 transition-colors"
			onClick={handleToggle}
		>
			<td className="px-3 py-2 text-center">
				{isExpanded ? (
					<ChevronDown className="w-4 h-4 text-muted-foreground" />
				) : (
					<ChevronRight className="w-4 h-4 text-muted-foreground" />
				)}
			</td>
			<td colSpan={8} className="px-2 py-2 font-medium">
				<div className="flex items-center gap-2">
					<span>
						{emoji} {catLabel}
					</span>
					<span className="text-[0.75rem] text-muted-foreground">
						({rulesCount} rules)
					</span>
					{activeCount > 0 && (
						<Badge
							variant="outline"
							className="text-[0.75rem] px-1.5 py-0.5 bg-signal-ask/10 text-signal-ask border border-signal-ask/25 font-semibold"
						>
							{activeCount} active · {totalFires} fires
						</Badge>
					)}
				</div>
			</td>
		</tr>
	);
});

interface RuleTableProps {
	grouped: Array<[string, { emoji: string; rules: RuleMetadata[] }]>;
	expandedCategories: Record<string, boolean>;
	toggleCategory: (catLabel: string) => void;
	selectedRuleId: string | null;
	onSelectRule: (ruleId: string) => void;
}

const RuleTable = memo(function RuleTable({
	grouped,
	expandedCategories,
	toggleCategory,
	selectedRuleId,
	onSelectRule,
}: RuleTableProps) {
	return (
		<div className="border border-border rounded-md bg-card/30 overflow-hidden text-[0.875rem]">
			<table className="w-full border-collapse">
				<thead>
					<tr className="border-b border-border text-muted-foreground text-[0.75rem] uppercase tracking-wider bg-card/50">
						<th className="px-3 py-2 text-left w-8" />
						<th className="px-2 py-2 text-left w-12">Hook</th>
						<th className="px-2 py-2 text-left w-12">CLI</th>
						<th className="px-3 py-2 text-left w-48">Rule ID</th>
						<th className="px-3 py-2 text-left">Title & Description</th>
						<th className="px-3 py-2 text-left w-20">Severity</th>
						<th className="px-3 py-2 text-left w-20">Action</th>
						<th className="px-3 py-2 text-right w-16">Fires</th>
						<th className="px-3 py-2 text-center w-20">Status</th>
					</tr>
				</thead>
				<tbody>
					{grouped.length === 0 ? (
						<tr>
							<td colSpan={9} className="text-center py-12 text-muted-foreground text-[0.875rem] italic">
								No rules match search or active filters.
							</td>
						</tr>
					) : (
						grouped.map(([catLabel, { emoji, rules }]) => {
							const isExpanded = expandedCategories[catLabel] !== false;
							const totalFires = rules.reduce((s, r) => s + r.fireCount, 0);
							const activeCount = rules.filter((r) => r.enabled && r.fireCount > 0).length;

							return (
								<Fragment key={catLabel}>
									<CategoryHeaderRow
										catLabel={catLabel}
										emoji={emoji}
										rulesCount={rules.length}
										activeCount={activeCount}
										totalFires={totalFires}
										isExpanded={isExpanded}
										onToggle={toggleCategory}
									/>
									{isExpanded &&
										rules.map((rule) => (
											<RuleRow
												key={rule.rule_id}
												rule={rule}
												isSelected={selectedRuleId === rule.rule_id}
												onSelectRule={onSelectRule}
												sevColor={SEVERITY_COLORS[rule.severity] ?? "hsl(210,20%,55%)"}
											/>
										))}
								</Fragment>
							);
						})
					)}
				</tbody>
			</table>
		</div>
	);
});

export const RuleList = memo(function RuleList({
	allRules,
	selectedRuleId,
	onSelectRule,
}: RuleListProps) {
	const [search, setSearch] = useState("");
	const [activeFilter, setActiveFilter] = useState<FilterType>("all");
	const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>({});

	const filteredRules = useMemo(() => {
		let list = allRules;

		switch (activeFilter) {
			case "hot":
				list = list.filter((r) => r.enabled && r.fireCount > 0);
				break;
			case "disabled":
				list = list.filter((r) => !r.enabled);
				break;
			case "partial":
				list = list.filter(
					(r) =>
						r.cliPartiallyEnabled ||
						(r.hookSupported && r.cliSupported && r.hookEnabled !== r.cliEnabled),
				);
				break;
			case "unsupported":
				list = list.filter((r) => !r.hookSupported || !r.cliSupported);
				break;
			case "changed":
				list = list.filter((r) => r.isChanged);
				break;
			default:
				break;
		}

		if (search) {
			const q = search.toLowerCase();
			list = list.filter(
				(r) =>
					r.rule_id.toLowerCase().includes(q) ||
					r.title.toLowerCase().includes(q) ||
					r.description.toLowerCase().includes(q) ||
					r.cliCounterparts.some((id) => id.toLowerCase().includes(q)) ||
					r.hookCounterparts.some((id) => id.toLowerCase().includes(q)),
			);
		}

		return list;
	}, [allRules, activeFilter, search]);

	const grouped = useMemo(() => {
		const map = new Map<string, { emoji: string; rules: RuleMetadata[] }>();
		for (const rule of filteredRules) {
			const cat = getCategory(rule.rule_id);
			if (!map.has(cat.label)) {
				map.set(cat.label, { emoji: cat.emoji, rules: [] });
			}
			map.get(cat.label)?.rules.push(rule);
		}

		return [...map.entries()].sort(([a], [b]) => categorySortIndex(a) - categorySortIndex(b));
	}, [filteredRules]);

	const toggleCategory = useCallback((catLabel: string) => {
		setExpandedCategories((prev) => ({
			...prev,
			[catLabel]: !prev[catLabel],
		}));
	}, []);

	const filterOptions = useMemo<Array<{ value: FilterType; label: string }>>(() => [
		{ value: "all", label: "All" },
		{ value: "hot", label: "Hot (Fired)" },
		{ value: "disabled", label: "Disabled" },
		{ value: "partial", label: "Partial" },
		{ value: "unsupported", label: "Unsupported" },
		{ value: "changed", label: "Changed" },
	], []);

	return (
		<div className="space-y-3 font-sans">
			<FilterBar
				search={search}
				onSearchChange={setSearch}
				activeFilter={activeFilter}
				onFilterChange={setActiveFilter}
				filterOptions={filterOptions}
			/>
			<RuleTable
				grouped={grouped}
				expandedCategories={expandedCategories}
				toggleCategory={toggleCategory}
				selectedRuleId={selectedRuleId}
				onSelectRule={onSelectRule}
			/>
		</div>
	);
});

export default RuleList;

