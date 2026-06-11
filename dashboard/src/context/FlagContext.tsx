import { type ReactNode, useCallback, useMemo, useState } from "react";
import type { FlagItemType, InvestigationFlag } from "@/types/slopgate";
import { FlagContext } from "./flagContext";

const STORAGE_KEY = "slopgate_flags";

function loadFlags(): InvestigationFlag[] {
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		return raw ? JSON.parse(raw) : [];
	} catch {
		return [];
	}
}

function saveFlags(flags: InvestigationFlag[]) {
	localStorage.setItem(STORAGE_KEY, JSON.stringify(flags));
}

export function FlagProvider({ children }: { children: ReactNode }) {
	const [flags, setFlags] = useState<InvestigationFlag[]>(loadFlags);

	const addFlag = useCallback(
		(item: Omit<InvestigationFlag, "id" | "createdAt" | "resolved">) => {
			setFlags((prev) => {
				const next = [
					...prev,
					{
						...item,
						id: `flag_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
						createdAt: new Date().toISOString(),
						resolved: false,
					},
				];
				saveFlags(next);
				return next;
			});
		},
		[],
	);

	const removeFlag = useCallback((id: string) => {
		setFlags((prev) => {
			const next = prev.filter((f) => f.id !== id);
			saveFlags(next);
			return next;
		});
	}, []);

	const resolveFlag = useCallback((id: string) => {
		setFlags((prev) => {
			const next = prev.map((f) =>
				f.id === id ? { ...f, resolved: true } : f,
			);
			saveFlags(next);
			return next;
		});
	}, []);

	const unresolveFlag = useCallback((id: string) => {
		setFlags((prev) => {
			const next = prev.map((f) =>
				f.id === id ? { ...f, resolved: false } : f,
			);
			saveFlags(next);
			return next;
		});
	}, []);

	const isFlagged = useCallback(
		(itemType: FlagItemType, itemId: string) => {
			return flags.some(
				(f) => f.itemType === itemType && f.itemId === itemId && !f.resolved,
			);
		},
		[flags],
	);

	const getFlagsForItem = useCallback(
		(itemType: FlagItemType, itemId: string) => {
			return flags.filter(
				(f) => f.itemType === itemType && f.itemId === itemId,
			);
		},
		[flags],
	);

	const exportFlags = useCallback(() => {
		const active = flags.filter((f) => !f.resolved);
		return active
			.map(
				(f) =>
					`# [${f.target}] ${f.itemType}:${f.itemId}\n` +
					`mode: ${f.mode}\n` +
					`label: ${f.label}\n` +
					(f.notes ? `notes: ${f.notes}\n` : "") +
					`flagged: ${f.createdAt}\n`,
			)
			.join("\n---\n\n");
	}, [flags]);

	const value = useMemo(
		() => ({
			flags,
			addFlag,
			removeFlag,
			resolveFlag,
			unresolveFlag,
			isFlagged,
			getFlagsForItem,
			exportFlags,
		}),
		[
			flags,
			addFlag,
			removeFlag,
			resolveFlag,
			unresolveFlag,
			isFlagged,
			getFlagsForItem,
			exportFlags,
		],
	);

	return <FlagContext.Provider value={value}>{children}</FlagContext.Provider>;
}
