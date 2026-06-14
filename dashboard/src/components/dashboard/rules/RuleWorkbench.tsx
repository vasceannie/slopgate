import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { useRulesConfig } from "@/context/useRulesConfig";
import type { SlopgateConfig } from "@/types/slopgate";
import { buildRuleMetadata, getRuleChangedFields } from "./model";
import { RuleCommandBand } from "./RuleCommandBand";
import { RuleInspector } from "./RuleInspector";
import { RuleList } from "./RuleList";

interface RuleWorkbenchProps {
	fireCounts: Map<string, number>;
}

function useMobileViewport() {
	const [isMobile, setIsMobile] = useState(false);
	useEffect(() => {
		const media = window.matchMedia("(max-width: 1023px)");
		setIsMobile(media.matches);
		const listener = (e: MediaQueryListEvent) => setIsMobile(e.matches);
		media.addEventListener("change", listener);
		return () => media.removeEventListener("change", listener);
	}, []);
	return isMobile;
}

function useRuleMetadataWithChanges(
	config: SlopgateConfig,
	savedConfig: SlopgateConfig,
	fireCounts: Map<string, number>,
) {
	return useMemo(() => {
		const rules = buildRuleMetadata(config, fireCounts);
		return rules.map((rule) => {
			const changedFields = getRuleChangedFields(rule.rule_id, savedConfig, config);
			return {
				...rule,
				changedFields,
				isChanged: changedFields.length > 0,
			};
		});
	}, [config, savedConfig, fireCounts]);
}

function useKeyDown(key: string, callback: () => void) {
	useEffect(() => {
		const handler = (e: KeyboardEvent) => {
			if (e.key === key) callback();
		};
		window.addEventListener("keydown", handler);
		return () => window.removeEventListener("keydown", handler);
	}, [key, callback]);
}


export const RuleWorkbench = memo(function RuleWorkbench({
	fireCounts,
}: RuleWorkbenchProps) {
	const {
		config,
		savedConfig,
		setRuleHookSurface,
		setRuleCliSurface,
		setExclusions,
	} = useRulesConfig();

	const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
	const isMobile = useMobileViewport();
	const allRules = useRuleMetadataWithChanges(config, savedConfig, fireCounts);

	const selectedRule = useMemo(() => {
		if (!selectedRuleId) return null;
		return allRules.find((r) => r.rule_id === selectedRuleId) ?? null;
	}, [selectedRuleId, allRules]);

	const handleSelectRule = useCallback((ruleId: string) => {
		setSelectedRuleId(ruleId);
	}, []);

	const handleCloseInspector = useCallback(() => {
		setSelectedRuleId(null);
	}, []);

	useKeyDown("Escape", handleCloseInspector);

	return (
		<div className="space-y-6 font-sans">
			<RuleCommandBand allRules={allRules} />
			<div className="flex flex-col lg:flex-row gap-4 items-stretch">
				<div className="flex-1 min-w-0">
					<RuleList
						allRules={allRules}
						selectedRuleId={selectedRuleId}
						onSelectRule={handleSelectRule}
					/>
				</div>
				{selectedRule && (
					<RuleInspector
						rule={selectedRule}
						onSetHookSurface={setRuleHookSurface}
						onSetRuleCliSurface={setRuleCliSurface}
						onExclusionsChange={setExclusions}
						onClose={handleCloseInspector}
						isMobile={isMobile}
					/>
				)}
			</div>
		</div>
	);
});

export default RuleWorkbench;

