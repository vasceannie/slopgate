import { useContext } from "react";
import { RulesConfigContext } from "./rulesConfigContext";

export function useRulesConfig() {
	const ctx = useContext(RulesConfigContext);
	if (!ctx)
		throw new Error("useRulesConfig must be used within RulesConfigProvider");
	return ctx;
}
