import { createContext } from "react";
import type { FlagItemType, InvestigationFlag } from "@/types/slopgate";

export interface FlagContextValue {
  flags: InvestigationFlag[];
  addFlag: (item: Omit<InvestigationFlag, "id" | "createdAt" | "resolved">) => void;
  removeFlag: (id: string) => void;
  resolveFlag: (id: string) => void;
  unresolveFlag: (id: string) => void;
  isFlagged: (itemType: FlagItemType, itemId: string) => boolean;
  getFlagsForItem: (itemType: FlagItemType, itemId: string) => InvestigationFlag[];
  exportFlags: () => string;
}

export const FlagContext = createContext<FlagContextValue | null>(null);
