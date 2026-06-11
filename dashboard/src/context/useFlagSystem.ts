import { useContext } from "react";
import { FlagContext } from "./flagContext";

export function useFlagSystem() {
	const ctx = useContext(FlagContext);
	if (!ctx) throw new Error("useFlagSystem must be used within FlagProvider");
	return ctx;
}
