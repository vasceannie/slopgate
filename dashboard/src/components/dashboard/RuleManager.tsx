import { RuleWorkbench } from "./rules/RuleWorkbench";

interface Props {
  /** Fire counts from trace data (rule_id → count) */
  fireCounts: Map<string, number>;
}

export function RuleManager({ fireCounts }: Props) {
  return <RuleWorkbench fireCounts={fireCounts} />;
}
