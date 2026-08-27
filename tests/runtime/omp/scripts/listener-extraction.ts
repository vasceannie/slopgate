import * as ts from "typescript";

import {
  ContractLockError,
  PLANNED_LISTENERS,
  type ListenerContract,
  type PlannedListener,
} from "./snapshot-schema.ts";
import { fieldsForType } from "./type-helpers.ts";

function requiredContract(
  contracts: ReadonlyMap<PlannedListener, ListenerContract>,
  listener: PlannedListener,
): ListenerContract {
  const contract = contracts.get(listener);
  if (!contract) throw new ContractLockError(`missing ExtensionAPI overload for ${listener}`);
  return contract;
}

export function extractListeners(
  source: ts.SourceFile,
  checker: ts.TypeChecker,
): Readonly<Record<PlannedListener, ListenerContract>> {
  const contracts = new Map<PlannedListener, ListenerContract>();
  const api = source.statements.find(
    (statement) => ts.isInterfaceDeclaration(statement) && statement.name.text === "ExtensionAPI",
  );
  if (!api || !ts.isInterfaceDeclaration(api)) throw new ContractLockError("missing ExtensionAPI interface");

  for (const member of api.members) {
    if (!ts.isMethodSignature(member) || member.name.getText(source) !== "on") continue;
    const eventType = member.parameters[0]?.type;
    const handlerType = member.parameters[1]?.type;
    if (!eventType || !ts.isLiteralTypeNode(eventType) || !ts.isStringLiteral(eventType.literal)) continue;
    const eventName = eventType.literal.text;
    const listener = PLANNED_LISTENERS.find((candidate) => candidate === eventName);
    if (!listener) continue;
    if (!handlerType || !ts.isTypeReferenceNode(handlerType)) {
      throw new ContractLockError(`listener ${listener} has an unresolved handler type`);
    }
    const resultNode = handlerType.typeArguments?.[1];
    const resultName = resultNode?.getText(source);
    contracts.set(listener, {
      fields: resultNode ? fieldsForType(checker.getTypeFromTypeNode(resultNode), checker) : {},
      result_union: resultName ? [resultName, "void"] : ["void"],
    });
  }

  return {
    agent_end: requiredContract(contracts, "agent_end"),
    before_agent_start: requiredContract(contracts, "before_agent_start"),
    input: requiredContract(contracts, "input"),
    session_start: requiredContract(contracts, "session_start"),
    session_stop: requiredContract(contracts, "session_stop"),
    tool_call: requiredContract(contracts, "tool_call"),
    tool_result: requiredContract(contracts, "tool_result"),
    turn_end: requiredContract(contracts, "turn_end"),
    user_bash: requiredContract(contracts, "user_bash"),
    user_python: requiredContract(contracts, "user_python"),
  };
}
