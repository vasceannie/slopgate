import { type DragEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";
import {
	Dialog,
	DialogContent,
	DialogDescription,
	DialogHeader,
	DialogTitle,
	DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	AlertTriangle,
	Check,
	CheckCircle2,
	Code2,
	Loader2,
	Paperclip,
	Plus,
	RefreshCw,
	Send,
	Sparkles,
	Terminal,
	X,
} from "lucide-react";

import { cn } from "@/lib/utils";
interface RuleIterationModalProps {
	isOpen: boolean;
	onClose: () => void;
	initialProjectName?: string;
	initialRepoRoot?: string | null;
	projects: Array<{ repoRoot: string; projectName: string }>;
	onRuleCreated?: (ruleData: { ruleId: string; projectName: string; path: string }) => void;
}

type ModalState = "setup" | "spawning" | "streaming" | "confirming" | "applied";

interface TerminalLog {
	type: "thought" | "command" | "result" | "system" | "user";
	text: string;
}

export function RuleIterationModal({
	isOpen,
	onClose,
	initialProjectName = "",
	projects,
	onRuleCreated,
}: RuleIterationModalProps) {
	// Form State
	const [selectedProject, setSelectedProject] = useState(initialProjectName || "all");
	const [hookTrigger, setHookTrigger] = useState("UserPromptSubmit");
	const [ruleName, setRuleName] = useState("");
	const [promptText, setPromptText] = useState("");
	const [fileInput, setFileInput] = useState("");
	const [fileRefs, setFileRefs] = useState<string[]>([]);
	const [attachments, setAttachments] = useState<string[]>([]);
	const [dragOver, setDragOver] = useState(false);

	// Runtime state
	const [modalState, setModalState] = useState<ModalState>("setup");
	const [logs, setLogs] = useState<TerminalLog[]>([]);
	const [diffContent, setDiffContent] = useState("");
	const [userInput, setUserInput] = useState("");
	const [isIterating, setIsIterating] = useState(false);
	const [iterationCount, setIterationCount] = useState(0);

	const terminalEndRef = useRef<HTMLDivElement>(null);

	// Get target repo details
	const targetProject = projects.find((p) => p.projectName === selectedProject) || {
		projectName: "slopgate",
		repoRoot: "/home/trav/.openclaw/workspace-hooker/slopgate",
	};

	// Reset form state on open
	useEffect(() => {
		if (isOpen) {
			setSelectedProject(initialProjectName || (projects[0]?.projectName ?? "slopgate"));
			setHookTrigger("UserPromptSubmit");
			setRuleName("");
			setPromptText("");
			setFileRefs([]);
			setAttachments([]);
			setModalState("setup");
			setLogs([]);
			setDiffContent("");
			setUserInput("");
			setIsIterating(false);
			setIterationCount(0);
		}
	}, [isOpen, initialProjectName, projects]);

	// Auto-scroll terminal logs
useEffect(() => {
if (terminalEndRef.current) {
terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
		}
		// Referencing logs length ensures effect runs when logs are updated
		const _ = logs.length;
}, [logs]);

	// File reference tag management
	const handleAddFileRef = () => {
		const val = fileInput.trim();
		if (val && !fileRefs.includes(val)) {
			setFileRefs([...fileRefs, val]);
		}
		setFileInput("");
	};

	const handleFileKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
		if (e.key === "Enter") {
			e.preventDefault();
			handleAddFileRef();
		}
	};

	const handleRemoveFileRef = (idx: number) => {
		setFileRefs(fileRefs.filter((_, i) => i !== idx));
	};

	// Drag and drop attachments
	const handleDragOver = (e: DragEvent) => {
		e.preventDefault();
		setDragOver(true);
	};

	const handleDragLeave = () => {
		setDragOver(false);
	};

	const handleDrop = (e: DragEvent) => {
		e.preventDefault();
		setDragOver(false);
		const files = Array.from(e.dataTransfer.files);
		if (files.length > 0) {
			const names = files.map((f) => f.name);
			setAttachments((prev) => [...prev, ...names]);
		}
	};

	const handleRemoveAttachment = (idx: number) => {
		setAttachments(attachments.filter((_, i) => i !== idx));
	};

	// Simulated workspace session spawning
	const startHermesSession = () => {
		if (!ruleName.trim() || !promptText.trim()) return;
		setModalState("spawning");
		setLogs([
			{ type: "system", text: "Connecting to Hermes session WebSocket..." },
			{ type: "system", text: `Project target: ${targetProject.projectName} (${targetProject.repoRoot})` },
		]);

		setTimeout(() => {
			setLogs((prev) => [
				...prev,
				{ type: "system", text: "Handshake established. Mounting isolated workspace sandbox..." },
			]);
		}, 600);

		setTimeout(() => {
			setLogs((prev) => [
				...prev,
				{ type: "system", text: "Workspace mounted. Querying file telemetry context..." },
				{ type: "command", text: "slopgate lint check --project-only" },
			]);
		}, 1300);

		setTimeout(() => {
			setLogs((prev) => [
				...prev,
				{ type: "result", text: "Active rules found: 23 builtins, 4 custom project-local definitions." },
				{ type: "system", text: "Beginning rule analysis stream..." },
			]);
			setModalState("streaming");
			streamRuleDetails();
		}, 2000);
	};

	// Simulated streaming rules & thoughts
	const streamRuleDetails = () => {
		const steps: Array<{ log: TerminalLog; diffChunk?: string; delay: number }> = [
			{
				log: { type: "thought", text: `Analyzing target hook trigger: ${hookTrigger} & rule goal...` },
				delay: 400,
			},
			{
				log: { type: "thought", text: `Scanning code references: ${fileRefs.length > 0 ? fileRefs.join(", ") : "general project scope"}...` },
				delay: 900,
			},
			{
				log: { type: "thought", text: "Structuring AST validation matcher for hook parameters..." },
				delay: 1500,
			},
			{
				log: { type: "command", text: `slopgate rule validate --draft --trigger ${hookTrigger}` },
				delay: 2000,
			},
			{
				log: { type: "result", text: "Syntax matches. Creating regex pattern rules." },
				diffChunk: `# Project-Specific Rule Definition for ${targetProject.projectName}\n# Target Hook Trigger: ${hookTrigger}\n# Generated via Hermes Iteration Session\n\n[rule.${ruleName.toUpperCase().replace(/\s+/g, "_")}]\ntitle = "${ruleName}"\nseverity = "MEDIUM"\nevents = ["${hookTrigger}"]\ntarget = "content"\npath_globs = ["src/**/*.ts", "src/**/*.tsx"]\nexclude_path_globs = [\n  "**/node_modules/**"\n]\n`,
				delay: 2500,
			},
			{
				log: { type: "thought", text: "Configuring default violation warning notification messages..." },
				diffChunk: `patterns = [\n  "function\\\\s+\\\\w+\\\\(.*\\\\)\\\\s*\\\\{"\n]\naction = "warn"\nmessage = "Verify if this pattern can be consolidated with existing utility modules."\n`,
				delay: 3200,
			},
			{
				log: { type: "system", text: "Interactive draft compiled successfully. Waiting for operator review." },
				delay: 3700,
			},
		];

		steps.forEach((step) => {
			setTimeout(() => {
				setLogs((prev) => [...prev, step.log]);
				if (step.diffChunk) {
					setDiffContent((prev) => prev + step.diffChunk);
				}
				if (step.log.type === "system" && step.log.text.includes("operator review")) {
					setModalState("confirming");
				}
			}, step.delay);
		});
	};

	// Interactive rule refinement (WebSocket dialogue loop)
	const handleSendIteration = () => {
		const text = userInput.trim();
		if (!text) return;

		setLogs((prev) => [...prev, { type: "user", text }]);
		setUserInput("");
		setIsIterating(true);

		// Simulate refined updates
		setTimeout(() => {
			setLogs((prev) => [
				...prev,
				{ type: "thought", text: `Refining rule PY-${ruleName.toUpperCase().replace(/\s+/g, "_")} based on feedback: "${text}"` },
			]);
		}, 500);

		setTimeout(() => {
			setLogs((prev) => [
				...prev,
				{ type: "command", text: "slopgate rule compile --check-tests" },
			]);
		}, 1200);

		setTimeout(() => {
			setLogs((prev) => [
				...prev,
				{ type: "result", text: "Rule exclusions modified. Regressions check clean." },
				{ type: "system", text: "Updated rule schema emitted below." },
			]);

			// Append exclusions to diff
			const newExclusions = `\n# Exclusions added via user feedback\nexclude_path_globs = [\n  "**/node_modules/**",\n  "**/test/**",\n  "**/*.test.ts"\n]\n`;
			setDiffContent((prev) => {
				// Strip previous exclude block if exists, replace with updated block
				const base = prev.replace(/exclude_path_globs = \[\n\s+"\*+\/node_modules\/\*+"\n\]\n/, "");
				return base + newExclusions;
			});

			setIsIterating(false);
			setIterationCount((c) => c + 1);
		}, 2000);
	};

	// Save/Apply rule
	const handleApproveRule = () => {
		setModalState("applied");
		if (onRuleCreated) {
			onRuleCreated({
				ruleId: `rule.${ruleName.toUpperCase().replace(/\s+/g, "_")}`,
				projectName: targetProject.projectName,
				path: `${targetProject.repoRoot}/.slopgate.toml`,
			});
		}
	};

	return (
		<Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
			<DialogContent className="max-w-4xl h-[650px] bg-background border border-border p-0 flex flex-col overflow-hidden text-foreground">
				<DialogHeader className="p-4 border-b border-border bg-card/40 flex flex-row items-center justify-between">
					<div className="space-y-0.5">
						<DialogTitle className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-1.5 uppercase">
							<Sparkles className="w-4 h-4 text-primary" />
							Rule & Hook Builder (Hermes/Pi Engine)
						</DialogTitle>
						<DialogDescription className="text-[10px] text-muted-foreground font-sans">
							Iterate and draft context-specific rules for hooks, CLI lints, and workspace policies.
						</DialogDescription>
					</div>
				</DialogHeader>

				{/* Phase 1: Configuration Form */}
				{modalState === "setup" && (
					<div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 md:grid-cols-[1.2fr_0.8fr] gap-8 font-sans">
						{/* Left Setup Form */}
						<div className="space-y-4">
							<div className="grid grid-cols-2 gap-4">
								<div className="space-y-1.5">
									<Label htmlFor="project-select" className="text-[10px] font-mono uppercase text-muted-foreground">
										Target Repository
									</Label>
									<Select value={selectedProject} onValueChange={setSelectedProject}>
										<SelectTrigger id="project-select" className="h-8 text-xs bg-muted/20 border-border/80 focus:ring-primary/40 focus:border-primary font-mono">
											<SelectValue placeholder="Select target project" />
										</SelectTrigger>
										<SelectContent className="bg-background border-border text-foreground font-mono text-xs">
											{projects.map((p) => (
												<SelectItem key={p.projectName} value={p.projectName}>
													{p.projectName}
												</SelectItem>
											))}
										</SelectContent>
									</Select>
								</div>

								<div className="space-y-1.5">
									<Label htmlFor="hook-trigger-select" className="text-[10px] font-mono uppercase text-muted-foreground">
										Hook Trigger Event
									</Label>
									<Select value={hookTrigger} onValueChange={setHookTrigger}>
										<SelectTrigger id="hook-trigger-select" className="h-8 text-xs bg-muted/20 border-border/80 focus:ring-primary/40 focus:border-primary font-mono">
											<SelectValue placeholder="Select trigger event" />
										</SelectTrigger>
										<SelectContent className="bg-background border-border text-foreground font-mono text-xs">
											<SelectItem value="UserPromptSubmit">UserPromptSubmit</SelectItem>
											<SelectItem value="PreToolUse">PreToolUse</SelectItem>
											<SelectItem value="PostToolUse">PostToolUse</SelectItem>
											<SelectItem value="PreWrite">PreWrite</SelectItem>
											<SelectItem value="PreCommit">PreCommit</SelectItem>
										</SelectContent>
									</Select>
								</div>
							</div>

							<div className="space-y-1.5">
								<Label htmlFor="rule-id-input" className="text-[10px] font-mono uppercase text-muted-foreground">
									Rule ID / Key Name
								</Label>
								<Input
									id="rule-id-input"
									placeholder="e.g. no-duplicate-helpers"
									value={ruleName}
									onChange={(e) => setRuleName(e.target.value)}
									className="h-8 text-xs font-mono bg-muted/20 border-border/80 focus-visible:ring-primary/40 focus-visible:border-primary"
								/>
							</div>

							<div className="space-y-1.5">
								<Label htmlFor="prompt-instruction-input" className="text-[10px] font-mono uppercase text-muted-foreground">
									Rule Goal / Instruction Prompt
								</Label>
								<Textarea
									id="prompt-instruction-input"
									placeholder="Describe what this rule is supposed to catch or enforce in detail. E.g., 'Verify if any function definition inside the parser folder duplicates parsing logics in common utilities.'"
									value={promptText}
									onChange={(e) => setPromptText(e.target.value)}
									className="h-24 text-xs bg-muted/20 border-border/80 focus-visible:ring-primary/40 focus-visible:border-primary min-h-[90px]"
								/>
							</div>

							<div className="space-y-1.5">
								<Label htmlFor="file-refs-input" className="text-[10px] font-mono uppercase text-muted-foreground flex items-center justify-between">
									<span>Codebase File References</span>
									<span className="text-[9px] lowercase text-muted-foreground/80">Press Enter to add tag</span>
								</Label>
								<div className="flex gap-2">
									<Input
										id="file-refs-input"
										placeholder="e.g. src/parser.ts, tests/helpers.ts"
										value={fileInput}
										onChange={(e) => setFileInput(e.target.value)}
										onKeyDown={handleFileKeyDown}
										className="h-8 text-xs font-mono bg-muted/20 border-border/80 focus-visible:ring-primary/40 focus-visible:border-primary"
									/>
									<Button
										type="button"
										size="sm"
										onClick={handleAddFileRef}
										className="h-8 text-[10px] font-mono px-3 bg-secondary hover:bg-secondary/90 text-secondary-foreground"
									>
										<Plus className="w-3.5 h-3.5 mr-1" />
										Add
									</Button>
								</div>
								{fileRefs.length > 0 && (
									<div className="flex flex-wrap gap-1.5 pt-1.5">
										{fileRefs.map((ref, idx) => (
											<Badge key={ref} variant="secondary" className="px-2 py-0.5 text-[9px] font-mono gap-1 border border-border/40 hover:bg-muted text-foreground">
												{ref}
												<button type="button" onClick={() => handleRemoveFileRef(idx)} className="text-muted-foreground hover:text-foreground">
													<X className="w-2.5 h-2.5" />
												</button>
											</Badge>
										))}
									</div>
								)}
							</div>
						</div>

						{/* Right Context & Attachments Sidebar */}
						<div className="space-y-5">
							{/* Drag & Drop Attachments */}
							<div className="space-y-1.5">
								<Label className="text-[10px] font-mono uppercase text-muted-foreground">
									Attachments (Logs, Lint Outputs)
								</Label>
								{/* biome-ignore lint/a11y/noStaticElementInteractions: drag/drop upload zone */}
								<div
									onDragOver={handleDragOver}
									onDragLeave={handleDragLeave}
									onDrop={handleDrop}
									className={cn(
										"border border-dashed rounded-lg p-5 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 min-h-[120px] bg-muted/5",
										dragOver ? "border-primary bg-primary/5" : "border-border/80 hover:bg-muted/10"
									)}
								>
									<Paperclip className="w-6 h-6 text-muted-foreground/85 mb-1.5" />
									<span className="text-[11px] font-semibold text-foreground">Drag files here</span>
									<span className="text-[9px] text-muted-foreground mt-0.5">Supports log files, text diagnostics</span>
								</div>
								{attachments.length > 0 && (
									<div className="space-y-1 pt-1.5">
										{attachments.map((name, idx) => (
											<div key={name} className="flex items-center justify-between p-1.5 bg-muted/20 border border-border/30 rounded text-[10px] font-mono">
												<span className="truncate max-w-[180px]">{name}</span>
												<button type="button" onClick={() => handleRemoveAttachment(idx)} className="text-muted-foreground hover:text-foreground">
													<X className="w-3.5 h-3.5" />
												</button>
											</div>
										))}
									</div>
								)}
							</div>

							{/* Context Helper Box */}
							<Card className="border border-border bg-card/25 p-3.5 rounded-lg space-y-2.5">
								<h5 className="text-[10px] font-semibold uppercase font-mono tracking-wider text-primary">
									Target Context Information
								</h5>
								<div className="space-y-1.5 text-[10px] font-mono leading-relaxed">
									<div>
										<span className="text-muted-foreground">Active Repo:</span>{" "}
										<span className="text-foreground font-semibold">{targetProject.projectName}</span>
									</div>
									<div className="truncate" title={targetProject.repoRoot}>
										<span className="text-muted-foreground">Root Path:</span>{" "}
										<span className="text-foreground">{targetProject.repoRoot}</span>
									</div>
									<div>
										<span className="text-muted-foreground">Rule Path:</span>{" "}
										<span className="text-foreground">
											{targetProject.projectName === "slopgate"
												? "~/.config/slopgate/config.json"
												: `${targetProject.projectName}/.slopgate.toml`}
										</span>
									</div>
								</div>
								<div className="text-[10px] text-muted-foreground leading-normal font-sans border-t border-border/40 pt-2.5">
									Hermes will analyze code paths, imports, and attachments to design a minimal rule syntax conforming to Slopgate parser standards.
								</div>
							</Card>
						</div>
					</div>
				)}

				{/* Phase 2: Loading / Active WebSocket streaming / Refinement dialogue */}
				{(modalState === "spawning" || modalState === "streaming" || modalState === "confirming") && (
					<div className="flex-1 overflow-hidden grid grid-cols-1 md:grid-cols-2 border-t border-border bg-card/10">
						{/* Left Terminal Log Streaming Window */}
						<div className="border-r border-border/60 flex flex-col overflow-hidden bg-black/45">
							<div className="p-2 border-b border-border bg-card/60 flex items-center justify-between text-[10px] uppercase font-mono text-muted-foreground">
								<span className="flex items-center gap-1.5">
									<Terminal className="w-3.5 h-3.5 text-primary" />
									Active Session: WebSocket Terminal
								</span>
								<Badge variant="outline" className={cn(
									"px-1.5 py-0 text-[8px] tracking-wide uppercase font-mono",
									modalState === "spawning" && "bg-muted text-muted-foreground animate-pulse",
									modalState === "streaming" && "bg-primary/5 text-primary border-primary/20 animate-pulse",
									modalState === "confirming" && "bg-signal-ask/5 text-signal-ask border-signal-ask/20"
								)}>
									{modalState}
								</Badge>
							</div>

							<div className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-[11px] leading-relaxed select-text">
								{logs.map((log, idx) => (
									<div
										// biome-ignore lint/suspicious/noArrayIndexKey: append-only terminal logs
										key={idx}
										className={cn(
											log.type === "thought" && "text-muted-foreground/90 italic",
											log.type === "command" && "text-primary font-semibold before:content-['$_']",
											log.type === "result" && "text-foreground bg-muted/10 p-1 rounded border border-border/20 pl-2",
											log.type === "system" && "text-signal-allow font-medium pl-2 border-l border-signal-allow/35",
											log.type === "user" && "text-signal-ask font-semibold pl-2 border-l border-signal-ask/35"
										)}
									>
										{log.type === "thought" && <span className="text-muted-foreground/60 mr-1">[thought]</span>}
										{log.text}
									</div>
								))}
								{modalState === "spawning" && (
									<div className="flex items-center gap-2 text-muted-foreground/60 animate-pulse mt-2">
										<Loader2 className="w-3 h-3 animate-spin text-primary" />
										<span>Awaiting session mount...</span>
									</div>
								)}
								<div ref={terminalEndRef} />
							</div>

							{/* User dialogue prompt input (only visible in confirming state) */}
							<div className="p-3 border-t border-border bg-card/30 flex gap-2 items-center">
								<Input
									placeholder={
										modalState === "confirming"
											? "Iterate on rule (e.g. 'exclude test files')"
											: "WebSocket session establishing..."
									}
									value={userInput}
									onChange={(e) => setUserInput(e.target.value)}
									disabled={modalState !== "confirming" || isIterating}
									onKeyDown={(e) => e.key === "Enter" && handleSendIteration()}
									className="h-8 text-xs font-sans bg-muted/20 border-border/80 focus-visible:ring-primary/40 focus-visible:border-primary flex-1"
								/>
								<Button
									size="sm"
									onClick={handleSendIteration}
									disabled={modalState !== "confirming" || isIterating || !userInput.trim()}
									className="h-8 px-3 bg-secondary hover:bg-secondary/90 text-secondary-foreground font-mono text-[10px]"
								>
									{isIterating ? (
										<Loader2 className="w-3.5 h-3.5 animate-spin" />
									) : (
										<>
											<Send className="w-3.5 h-3.5 mr-1" />
											Send
										</>
									)}
								</Button>
							</div>
						</div>

						{/* Right Code Diff / Editor Pane */}
						<div className="flex flex-col overflow-hidden bg-zinc-950">
							<div className="p-2 border-b border-border bg-card/60 flex items-center justify-between text-[10px] uppercase font-mono text-muted-foreground">
								<span className="flex items-center gap-1.5">
									<Code2 className="w-3.5 h-3.5 text-primary" />
									Draft Rule (Diff / Spec Schema)
								</span>
								<span className="text-[9px] text-muted-foreground normal-case font-mono">
									{targetProject.projectName}/.slopgate.toml
								</span>
							</div>

							<div className="flex-1 p-4 overflow-y-auto font-mono text-[10.5px] leading-relaxed text-slate-300 select-text whitespace-pre bg-black/10">
								{diffContent ? (
									diffContent
								) : (
									<div className="h-full flex flex-col items-center justify-center text-muted-foreground/60 space-y-1 font-sans">
										<Code2 className="w-6 h-6 text-muted-foreground/40 animate-pulse" />
										<span>Awaiting rule generation...</span>
									</div>
								)}
							</div>
						</div>
					</div>
				)}

				{/* Phase 3: Applied Success State */}
				{modalState === "applied" && (
					<div className="flex-1 p-8 flex flex-col items-center justify-center text-center space-y-4 max-w-xl mx-auto font-sans">
						<div className="w-12 h-12 rounded-full bg-signal-allow/15 flex items-center justify-center text-signal-allow animate-bounce">
							<CheckCircle2 className="w-8 h-8" />
						</div>
						<div className="space-y-1.5">
							<h3 className="text-sm font-semibold text-foreground uppercase tracking-wider font-sans">
								Rule Appended Successfully!
							</h3>
							<p className="text-[11px] text-muted-foreground leading-relaxed">
								The project-specific rule <code className="font-mono bg-muted px-1.5 py-0.5 rounded border border-border/40 text-foreground">PY-{ruleName.toUpperCase().replace(/\s+/g, "_")}</code> has been compiled and appended to the workspace context.
							</p>
						</div>

						<Card className="border border-border bg-card/30 p-4 w-full text-left font-mono text-[10.5px] leading-relaxed space-y-1.5">
							<div>
								<span className="text-muted-foreground">Status:</span>{" "}
								<span className="text-signal-allow font-semibold">Active (strict mode)</span>
							</div>
							<div>
								<span className="text-muted-foreground">Project:</span>{" "}
								<span className="text-foreground">{targetProject.projectName}</span>
							</div>
							<div>
								<span className="text-muted-foreground">Config Target:</span>{" "}
								<span className="text-foreground truncate">{targetProject.repoRoot}/.slopgate.toml</span>
							</div>
							<div className="border-t border-border/40 pt-2 text-[10px] text-muted-foreground font-sans">
								Pre-commit and Pre-write hook triggers will execute this rule validation on workspace actions.
							</div>
						</Card>

						<div className="flex gap-3 pt-2 w-full">
							<Button
								variant="outline"
								onClick={() => {
									setModalState("setup");
									setLogs([]);
									setDiffContent("");
									setRuleName("");
									setPromptText("");
								}}
								className="flex-1 h-8 text-[10px] uppercase font-mono border-border text-muted-foreground hover:bg-muted"
							>
								<RefreshCw className="w-3.5 h-3.5 mr-1" />
								Draft Another
							</Button>
							<Button
								onClick={onClose}
								className="flex-1 h-8 text-[10px] uppercase font-mono bg-primary text-primary-foreground hover:bg-primary/95"
							>
								<Check className="w-3.5 h-3.5 mr-1" />
								Done
							</Button>
						</div>
					</div>
				)}

				{/* Modal Actions Footer */}
				{modalState === "setup" && (
					<DialogFooter className="p-4 border-t border-border bg-card/40 flex items-center justify-between gap-3 sm:space-x-0">
						<div className="flex items-center gap-1.5 text-[10px] text-muted-foreground font-sans mr-auto">
							<AlertTriangle className="w-3.5 h-3.5 text-signal-ask" />
							<span>Requires prompt and rule name to initialize Hermes container session.</span>
						</div>
						<div className="flex gap-2">
							<Button
								type="button"
								variant="outline"
								onClick={onClose}
								className="h-8 text-[10px] uppercase font-mono px-3.5 border-border hover:bg-muted text-muted-foreground"
							>
								Cancel
							</Button>
							<Button
								type="button"
								onClick={startHermesSession}
								disabled={!ruleName.trim() || !promptText.trim()}
								className="h-8 text-[10px] uppercase font-mono px-4 bg-primary text-primary-foreground hover:bg-primary/95 gap-1.5"
							>
								<Sparkles className="w-3.5 h-3.5" />
								Start Hermes Session
							</Button>
						</div>
					</DialogFooter>
				)}

				{modalState === "confirming" && (
					<DialogFooter className="p-4 border-t border-border bg-card/40 flex items-center justify-between gap-3 sm:space-x-0">
						<div className="flex items-center gap-1.5 text-[10px] text-muted-foreground font-sans mr-auto">
							<CheckCircle2 className="w-3.5 h-3.5 text-signal-allow animate-pulse" />
							<span>Rule compiled successfully. {iterationCount > 0 ? `${iterationCount} iterations` : "Ready to apply."}</span>
						</div>
						<div className="flex gap-2">
							<Button
								type="button"
								variant="outline"
								onClick={() => setModalState("setup")}
								className="h-8 text-[10px] uppercase font-mono px-3.5 border-border hover:bg-muted text-muted-foreground"
							>
								Back to Setup
							</Button>
							<Button
								type="button"
								onClick={handleApproveRule}
								className="h-8 text-[10px] uppercase font-mono px-4 bg-primary text-primary-foreground hover:bg-primary/95 gap-1.5"
							>
								<Check className="w-3.5 h-3.5" />
								Approve & Apply
							</Button>
						</div>
					</DialogFooter>
				)}
			</DialogContent>
		</Dialog>
	);
}
