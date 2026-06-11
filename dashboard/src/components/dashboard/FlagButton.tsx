import { Clock, Flag, Radio, Target, X } from "lucide-react";
import { useCallback, useState } from "react";
import { useFlagSystem } from "@/context/useFlagSystem";
import { FLAG_TARGET_LABELS } from "@/lib/chartTheme";
import { cn } from "@/lib/utils";
import type { FlagItemType, FlagMode, FlagTarget } from "@/types/slopgate";

const MODE_LABELS: Record<FlagMode, { label: string; icon: typeof Target }> = {
	"on-direction": { label: "On Direction", icon: Target },
	cron: { label: "Cron", icon: Clock },
	heartbeat: { label: "Heartbeat", icon: Radio },
};

interface Props {
	itemType: FlagItemType;
	itemId: string;
	label: string;
	compact?: boolean;
}

export function FlagButton({ itemType, itemId, label, compact }: Props) {
	const { isFlagged, addFlag, getFlagsForItem, removeFlag } = useFlagSystem();
	const [showPanel, setShowPanel] = useState(false);
	const [target, setTarget] = useState<FlagTarget>("claude");
	const [mode, setMode] = useState<FlagMode>("on-direction");
	const [notes, setNotes] = useState("");

	const flagged = isFlagged(itemType, itemId);
	const existingFlags = getFlagsForItem(itemType, itemId);

	const handleSubmit = useCallback(() => {
		addFlag({ itemType, itemId, label, target, mode, notes });
		setShowPanel(false);
		setNotes("");
	}, [addFlag, itemType, itemId, label, target, mode, notes]);

	const togglePanel = useCallback((e: React.MouseEvent) => {
		e.stopPropagation();
		setShowPanel((v) => !v);
	}, []);

	const closePanel = useCallback(() => setShowPanel(false), []);

	if (compact) {
		return (
			<div className="relative">
				<button
					type="button"
					onClick={togglePanel}
					className={cn(
						"p-0.5 rounded transition-colors",
						flagged
							? "text-signal-ask"
							: "text-muted-foreground/40 hover:text-signal-ask",
					)}
					title="Flag for investigation"
				>
					<Flag className="w-3 h-3" fill={flagged ? "currentColor" : "none"} />
				</button>
				{showPanel && (
					<FlagPanel
						{...{
							target,
							setTarget,
							mode,
							setMode,
							notes,
							setNotes,
							handleSubmit,
							existingFlags,
							removeFlag,
							onClose: closePanel,
						}}
					/>
				)}
			</div>
		);
	}

	return (
		<div className="relative inline-flex">
			<button
				type="button"
				onClick={togglePanel}
				className={cn(
					"flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] transition-colors",
					flagged
						? "bg-signal-ask/10 text-signal-ask"
						: "text-muted-foreground hover:bg-muted hover:text-foreground",
				)}
			>
				<Flag className="w-3 h-3" fill={flagged ? "currentColor" : "none"} />
				{flagged ? "Flagged" : "Flag"}
			</button>
			{showPanel && (
				<FlagPanel
					{...{
						target,
						setTarget,
						mode,
						setMode,
						notes,
						setNotes,
						handleSubmit,
						existingFlags,
						removeFlag,
						onClose: closePanel,
					}}
				/>
			)}
		</div>
	);
}

function FlagPanel({
	target,
	setTarget,
	mode,
	setMode,
	notes,
	setNotes,
	handleSubmit,
	existingFlags,
	removeFlag,
	onClose,
}: {
	target: FlagTarget;
	setTarget: (t: FlagTarget) => void;
	mode: FlagMode;
	setMode: (m: FlagMode) => void;
	notes: string;
	setNotes: (n: string) => void;
	handleSubmit: () => void;
	existingFlags: Array<{
		id: string;
		target: FlagTarget;
		mode: FlagMode;
		notes: string;
		resolved: boolean;
	}>;
	removeFlag: (id: string) => void;
	onClose: () => void;
}) {
	return (
		<div
			aria-label="Flag investigation panel"
			className="absolute right-0 top-full mt-1 z-50 w-72 bg-card border border-border rounded-md shadow-lg p-3 space-y-3"
			onClick={(e) => e.stopPropagation()}
			onKeyDown={(e) => e.stopPropagation()}
			role="dialog"
		>
			<div className="flex items-center justify-between">
				<span className="text-xs font-medium flex items-center gap-1.5">
					<Flag className="w-3 h-3 text-signal-ask" />
					Flag for Investigation
				</span>
				<button
					type="button"
					onClick={onClose}
					className="text-muted-foreground hover:text-foreground"
				>
					<X className="w-3 h-3" />
				</button>
			</div>

			<div>
				<div className="text-[10px] text-muted-foreground uppercase mb-1">
					Target Agent
				</div>
				<div className="flex gap-1">
					{(
						Object.entries(FLAG_TARGET_LABELS) as [
							FlagTarget,
							(typeof FLAG_TARGET_LABELS)[FlagTarget],
						][]
					).map(([key, { label, color }]) => (
						<button
							type="button"
							key={key}
							onClick={() => setTarget(key)}
							className={cn(
								"px-2 py-1 rounded text-[10px] transition-colors",
								target === key
									? `bg-muted ${color} font-medium`
									: "text-muted-foreground hover:bg-muted/50",
							)}
						>
							{label}
						</button>
					))}
				</div>
			</div>

			<div>
				<div className="text-[10px] text-muted-foreground uppercase mb-1">
					Trigger Mode
				</div>
				<div className="flex gap-1">
					{(
						Object.entries(MODE_LABELS) as [
							FlagMode,
							(typeof MODE_LABELS)[FlagMode],
						][]
					).map(([key, { label, icon: Icon }]) => (
						<button
							type="button"
							key={key}
							onClick={() => setMode(key)}
							className={cn(
								"flex items-center gap-1 px-2 py-1 rounded text-[10px] transition-colors",
								mode === key
									? "bg-muted text-foreground font-medium"
									: "text-muted-foreground hover:bg-muted/50",
							)}
						>
							<Icon className="w-3 h-3" />
							{label}
						</button>
					))}
				</div>
			</div>

			<div>
				<div className="text-[10px] text-muted-foreground uppercase mb-1">
					Notes (optional)
				</div>
				<textarea
					value={notes}
					onChange={(e) => setNotes(e.target.value)}
					placeholder="What should the agent look at?"
					className="w-full h-14 bg-muted/30 border border-border rounded px-2 py-1.5 text-xs resize-none focus:outline-none focus:ring-1 focus:ring-primary"
				/>
			</div>

			<button
				type="button"
				onClick={handleSubmit}
				className="w-full py-1.5 bg-signal-ask/20 text-signal-ask rounded text-xs font-medium hover:bg-signal-ask/30 transition-colors"
			>
				Add Flag
			</button>

			{existingFlags.length > 0 && (
				<div className="space-y-1.5 border-t border-border pt-2">
					<div className="text-[10px] text-muted-foreground uppercase">
						Existing Flags
					</div>
					{existingFlags.map((f) => (
						<div
							key={f.id}
							className={cn(
								"flex items-center justify-between px-2 py-1 rounded text-[10px]",
								f.resolved ? "bg-muted/20 opacity-50" : "bg-muted/40",
							)}
						>
							<span>
								<span className={FLAG_TARGET_LABELS[f.target].color}>
									{FLAG_TARGET_LABELS[f.target].label}
								</span>
								<span className="text-muted-foreground mx-1">·</span>
								<span className="text-muted-foreground">{f.mode}</span>
							</span>
							<button
								type="button"
								onClick={() => removeFlag(f.id)}
								className="text-muted-foreground hover:text-signal-block"
							>
								<X className="w-3 h-3" />
							</button>
						</div>
					))}
				</div>
			)}
		</div>
	);
}
