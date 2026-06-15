import type { Severity, RuleFinding, HookResult, Decision } from "@/types/slopgate";
import { resolveDecision } from "@/hooks/useTraceData";

export type CalibrationMode = "advisory" | "error" | "variance";

export type CalibrationConfidence = "low" | "medium" | "high";

const RECURRENCE_BASE_WEIGHT = 45;
const RECURRENCE_INTENSITY_WEIGHT = 35;
const RECURRENCE_BREADTH_WEIGHT = 20;
const FINDINGS_PER_SESSION_SCORE_SCALE = 20;
const SESSION_BREADTH_SCORE_SCALE = 20;
const RUNTIME_ERROR_BASE_SCORE = 30;
const RUNTIME_ERROR_WEIGHT = 70;
const RUNTIME_ERROR_SCORE_SCALE = 5;

export interface RuleCalibrationSignal {
	rule_id: string;
	advisoryPressure: number; // 0-100
	runtimeErrorPressure: number; // 0-100, raw repeat-firing triage score
	decisionVariance: number; // 0-100, delivered persistence triage score
	confidence: CalibrationConfidence;
	totalFindings: number;
	blockCount: number;
	warnCount: number;
	allowCount: number;
	allowAfterWarn: number;
	repeatFireSessions: number;
	deliveredSessions: number;
	persistentDeliveredFindings: number;
	runtimeErrorCount: number;
	severity: Severity;
	sessionsCount: number;
	isAdvisorySuspect: boolean;
	isRuntimeErrorSuspect: boolean;
	isVariableSuspect: boolean;
	isClean: boolean;
	recentExampleMessage?: string | null;
	recentExampleError?: string | null;
}

function stableValue(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(stableValue);
	if (value && typeof value === "object") {
		return Object.fromEntries(
			Object.entries(value as Record<string, unknown>)
				.sort(([left], [right]) => left.localeCompare(right))
				.map(([key, child]) => [key, stableValue(child)]),
		);
	}
	return value;
}

function resultScopeKey(result: HookResult): string {
	return JSON.stringify({
		event_name: result.event_name,
		tool_name: result.tool_name,
		command: result.command ?? null,
		tool_input: stableValue(result.tool_input ?? null),
	});
}

function findingsForRule(result: HookResult, ruleId: string) {
	return result.findings.filter((finding) => finding.rule_id === ruleId);
}

function asymptoticRatio(value: number, scale: number): number {
	if (value <= 0 || scale <= 0) return 0;
	return 1 - Math.exp(-value / scale);
}

function recurrenceScore({
	rate,
	averageFindingsPerSession,
	sessions,
}: {
	rate: number;
	averageFindingsPerSession: number;
	sessions: number;
}): number {
	if (rate <= 0) return 0;
	const intensity = asymptoticRatio(
		averageFindingsPerSession,
		FINDINGS_PER_SESSION_SCORE_SCALE,
	);
	const breadth = asymptoticRatio(sessions, SESSION_BREADTH_SCORE_SCALE);
	return Math.min(
		100,
		Math.round(
			rate *
				(
					RECURRENCE_BASE_WEIGHT +
					intensity * RECURRENCE_INTENSITY_WEIGHT +
					breadth * RECURRENCE_BREADTH_WEIGHT
				),
		),
	);
}

export function computeCalibrationSignals(
	rules: RuleFinding[],
	results: HookResult[],
): RuleCalibrationSignal[] {
	const byRule = new Map<string, RuleFinding[]>();
	const knownRuleIds = new Set<string>();
	const upperToOriginalRuleId = new Map<string, string>();
	const resultsBySession = new Map<string, HookResult[]>();

	for (const r of results) {
		if (!resultsBySession.has(r.session_id)) {
			resultsBySession.set(r.session_id, []);
		}
		resultsBySession.get(r.session_id)?.push(r);
	}
	for (const sessionResults of resultsBySession.values()) {
		sessionResults.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
	}

	for (const r of rules) {
		if (!byRule.has(r.rule_id)) byRule.set(r.rule_id, []);
		byRule.get(r.rule_id)?.push(r);
		knownRuleIds.add(r.rule_id);
		upperToOriginalRuleId.set(r.rule_id.toUpperCase(), r.rule_id);
	}

	for (const r of results) {
		for (const f of r.findings) {
			knownRuleIds.add(f.rule_id);
			upperToOriginalRuleId.set(f.rule_id.toUpperCase(), f.rule_id);
		}
	}
	const sessionFinalDecision = new Map<string, Decision>();
	for (const r of results) {
		const d = resolveDecision(r.findings);
		const existing = sessionFinalDecision.get(r.session_id);
		if (!existing || d === "block" || d === "deny") {
			sessionFinalDecision.set(r.session_id, d);
		}
	}

	const errorsByRule = new Map<string, number>();
	const parsedErrorSamples = new Map<string, string[]>();

	for (const r of results) {
		for (const err of r.errors ?? []) {
			const match = err.match(/^([A-Za-z0-9_-]+):\s*(.*)/s);
			let matchedRuleId: string | null = null;
			let cleanErrMsg = err;
			if (match) {
				const potentialId = match[1].toUpperCase();
				const originalId = upperToOriginalRuleId.get(potentialId);
				if (originalId) {
					matchedRuleId = originalId;
					cleanErrMsg = match[2];
				} else if (/^[A-Z0-9]+-[A-Z0-9_-]+$/.test(potentialId)) {
					const lower = potentialId.toLowerCase();
					let foundCaseInsensitive = false;
					for (const kid of knownRuleIds) {
						if (kid.toUpperCase() === potentialId) {
							matchedRuleId = kid;
							foundCaseInsensitive = true;
							break;
						}
					}
					if (!foundCaseInsensitive) {
						const isUppercasePrefix = /^(PY|BUILTIN|STOP|GLOBAL|LG|TS|FE|RS|GIT|SHELL|QA|WARN|CONFIG|STYLE|REMIND)-/i.test(potentialId);
						matchedRuleId = isUppercasePrefix ? potentialId : lower;
					}
					cleanErrMsg = match[2];
				}
			}
			if (matchedRuleId) {
				errorsByRule.set(matchedRuleId, (errorsByRule.get(matchedRuleId) || 0) + 1);
				let samples = parsedErrorSamples.get(matchedRuleId);
				if (!samples) {
					samples = [];
					parsedErrorSamples.set(matchedRuleId, samples);
				}
				if (samples.length < 5) {
					samples.push(cleanErrMsg);
				}
			}
		}
	}

	const signals: RuleCalibrationSignal[] = [];
	const allRuleIds = new Set<string>([...byRule.keys(), ...errorsByRule.keys()]);

	for (const rule_id of allRuleIds) {
		const findings = byRule.get(rule_id) || [];
		const totalFindings = findings.length;

		const decisions = findings.map((f) => f.decision ?? "context");
		const blockCount = decisions.filter(
			(d) => d === "block" || d === "deny",
		).length;
		const warnCount = decisions.filter(
			(d) => d === "warn" || d === "context" || d === "ask" || d === "info",
		).length;
		const allowCount = decisions.filter((d) => d === "allow").length;

		const sessionsWithRule = [...new Set(findings.map((f) => f.session_id))];
		const sessionsCount = sessionsWithRule.length;

		const allowAfterWarn = sessionsWithRule.filter((sid) => {
			const ruleDecisions = findings
				.filter((f) => f.session_id === sid)
				.map((f) => f.decision ?? "context");
			const hadWarning = ruleDecisions.some(
				(d) => d === "warn" || d === "ask" || d === "context" || d === "info",
			);
			const sessionDecision = sessionFinalDecision.get(sid);
			const sessionAllowed = sessionDecision !== "block" && sessionDecision !== "deny" && sessionDecision !== "ask";
			return hadWarning && sessionAllowed;
		}).length;

		// 1. advisoryPressure
		const warnRatio = totalFindings > 0 ? warnCount / totalFindings : 0;
		const allowAfterWarnRatio = sessionsCount > 0 ? allowAfterWarn / sessionsCount : 0;
		const sampleSizeConfidence = Math.min(sessionsCount / 5, 1.0);
		const advisoryPressure = Math.min(
			100,
			Math.round((allowAfterWarnRatio * 60 + warnRatio * 40) * sampleSizeConfidence),
		);

		// Group findings of this rule by session_id
		const findingsBySession = new Map<string, RuleFinding[]>();
		for (const f of findings) {
			if (!findingsBySession.has(f.session_id)) {
				findingsBySession.set(f.session_id, []);
			}
			findingsBySession.get(f.session_id)?.push(f);
		}

		let activeSessionsCount = 0;
		let multiWarnSessionsCount = 0;
		let deliveredSessions = 0;
		let totalDeliveredCreated = 0;
		let totalPersistentDelivered = 0;

		for (const [sid, sessionFindings] of findingsBySession.entries()) {
			activeSessionsCount++;

			// Sort findings in this session by timestamp
			sessionFindings.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

			// Unique runs where the rule fired in this session (by timestamp)
			const uniqueRunTimes = [...new Set(sessionFindings.map((f) => f.timestamp))];
			if (uniqueRunTimes.length > 1) {
				multiWarnSessionsCount++;
			}


			const deliveredResults = (resultsBySession.get(sid) || []).filter(
				(result) => findingsForRule(result, rule_id).length > 0,
			);
			if (deliveredResults.length === 0) continue;

			deliveredSessions++;
			const firstDelivered = deliveredResults[0];
			const firstDeliveredFindings = findingsForRule(firstDelivered, rule_id).length;
			const scopeKey = resultScopeKey(firstDelivered);
			const comparableResults = (resultsBySession.get(sid) || []).filter(
				(result) => resultScopeKey(result) === scopeKey,
			);
			const lastComparableResult = comparableResults[comparableResults.length - 1];
			const persistentFindings = lastComparableResult
				? findingsForRule(lastComparableResult, rule_id).length
				: firstDeliveredFindings;

			totalDeliveredCreated += firstDeliveredFindings;
			totalPersistentDelivered += persistentFindings;
		}

		// 2. runtimeErrorPressure (repurposed as raw repeat-firing triage score)
		const repeatFireRate = activeSessionsCount > 0
			? multiWarnSessionsCount / activeSessionsCount
			: 0;
		const repeatFirePressure = recurrenceScore({
			rate: repeatFireRate,
			averageFindingsPerSession: activeSessionsCount > 0
				? totalFindings / activeSessionsCount
				: 0,
			sessions: activeSessionsCount,
		});
		const runtimeErrorCount = errorsByRule.get(rule_id) || 0;
		const runtimeErrorRatio = asymptoticRatio(
			runtimeErrorCount,
			RUNTIME_ERROR_SCORE_SCALE,
		);
		const runtimeErrorPressureFromErrors = runtimeErrorCount > 0
			? Math.min(
				100,
				RUNTIME_ERROR_BASE_SCORE +
					Math.round(runtimeErrorRatio * RUNTIME_ERROR_WEIGHT),
			)
			: 0;
		const runtimeErrorPressure = Math.max(
			repeatFirePressure,
			runtimeErrorPressureFromErrors,
		);
		// 3. decisionVariance (repurposed as delivered persistence triage score)
		const persistenceRate = totalDeliveredCreated > 0
			? Math.min(1, totalPersistentDelivered / totalDeliveredCreated)
			: 0;
		const decisionVariance = recurrenceScore({
			rate: persistenceRate,
			averageFindingsPerSession: deliveredSessions > 0
				? totalPersistentDelivered / deliveredSessions
				: 0,
			sessions: deliveredSessions,
		});

		// 4. confidence
		let confidence: CalibrationConfidence = "low";
		if (totalFindings > 0) {
			if (sessionsCount >= 8 && totalFindings >= 10) {
				confidence = "high";
			} else if (sessionsCount >= 3 && totalFindings >= 4) {
				confidence = "medium";
			}
		}

		// Suspect categories
		const isAdvisorySuspect = advisoryPressure > 30;
		const isRuntimeErrorSuspect = runtimeErrorPressure > 30;
		const isVariableSuspect = decisionVariance > 30;
		const isClean = !isAdvisorySuspect && !isRuntimeErrorSuspect && !isVariableSuspect;

		// severity fallback
		let severity: Severity = "MEDIUM";
		if (totalFindings > 0) {
			severity = findings[0].severity;
		} else {
			// fallback check from results
			let foundSeverity: Severity | null = null;
			for (const r of results) {
				const f = r.findings.find((x) => x.rule_id === rule_id);
				if (f) {
					foundSeverity = f.severity;
					break;
				}
			}
			if (foundSeverity) {
				severity = foundSeverity;
			}
		}

		const messageFinding = findings.find((f) => f.message);
		const recentExampleMessage = messageFinding ? messageFinding.message : null;

		const errorSamples = parsedErrorSamples.get(rule_id) || [];
		const recentExampleError = errorSamples.length > 0 ? errorSamples[0] : null;

		signals.push({
			rule_id,
			advisoryPressure,
			runtimeErrorPressure,
			decisionVariance,
			confidence,
			totalFindings,
			blockCount,
			warnCount,
			allowCount,
			allowAfterWarn,
			repeatFireSessions: multiWarnSessionsCount,
			deliveredSessions,
			persistentDeliveredFindings: totalPersistentDelivered,
			runtimeErrorCount,
			severity,
			sessionsCount,
			isAdvisorySuspect,
			isRuntimeErrorSuspect,
			isVariableSuspect,
			isClean,
			recentExampleMessage,
			recentExampleError,
		});
	}

	return signals;
}
