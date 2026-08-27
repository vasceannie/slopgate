import { join } from "node:path";

import { expandBashVariants } from "./bash-variants.ts";
import { extractListeners } from "./listener-extraction.ts";
import { ContractLockError, type ContractSnapshot } from "./snapshot-schema.ts";
import {
  createDeclarationProgram,
  extractContentUnion,
  extractEventNames,
  fieldsForType,
  findNamedType,
  requireSource,
} from "./type-helpers.ts";

type ExtractionResult = {
  readonly bashInput: ContractSnapshot["bash_input"];
  readonly eventNames: readonly string[];
  readonly listeners: ContractSnapshot["listeners"];
  readonly results: ContractSnapshot["results"];
  readonly sessionStopContentUnion: readonly string[];
  readonly sessionStopEvent: ContractSnapshot["session_stop"]["event"];
};

function assertFields(fields: Readonly<Record<string, unknown>>, names: readonly string[], label: string): void {
  const actual = Object.keys(fields).sort();
  const expected = [...names].sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new ContractLockError(`${label} fields changed: ${actual.join(",")}`);
  }
}

export function extractTypeContract(packageRoot: string): ExtractionResult {
  const typesPath = join(packageRoot, "dist/types/extensibility/extensions/types.d.ts");
  const sharedPath = join(packageRoot, "dist/types/extensibility/shared-events.d.ts");
  const bashPath = join(packageRoot, "dist/types/tools/bash.d.ts");
  const program = createDeclarationProgram([typesPath, sharedPath, bashPath]);
  const checker = program.getTypeChecker();
  const typesSource = requireSource(program, typesPath);
  const sharedSource = requireSource(program, sharedPath);
  const bashSource = requireSource(program, bashPath);
  const eventNames = extractEventNames(findNamedType(typesSource, "ExtensionEvent", checker), checker);
  if (!eventNames.includes("user_bash") || !eventNames.includes("user_python")) {
    throw new ContractLockError("pinned event union must contain user_bash and user_python");
  }

  const sessionStopType = findNamedType(sharedSource, "SessionStopEvent", checker);
  const sessionStopFields = fieldsForType(sessionStopType, checker);
  for (const requiredField of ["last_assistant_message", "session_id", "stop_hook_active"] as const) {
    if (!(requiredField in sessionStopFields)) throw new ContractLockError(`SessionStopEvent lacks ${requiredField}`);
  }
  const results: ContractSnapshot["results"] = {
    BeforeAgentStartEventResult: {
      fields: fieldsForType(findNamedType(typesSource, "BeforeAgentStartEventResult", checker), checker),
    },
    InputEventResult: { fields: fieldsForType(findNamedType(typesSource, "InputEventResult", checker), checker) },
    SessionStopEventResult: {
      fields: fieldsForType(findNamedType(sharedSource, "SessionStopEventResult", checker), checker),
    },
    ToolCallEventResult: {
      fields: fieldsForType(findNamedType(sharedSource, "ToolCallEventResult", checker), checker),
    },
  };
  assertFields(results.InputEventResult.fields, ["handled", "images", "text"], "InputEventResult");
  assertFields(results.ToolCallEventResult.fields, ["block", "input", "reason"], "ToolCallEventResult");
  if ("stop_hook_active" in results.SessionStopEventResult.fields) {
    throw new ContractLockError("SessionStopEventResult contains input-only stop_hook_active");
  }
  assertFields(
    results.SessionStopEventResult.fields,
    ["additionalContext", "continue", "decision", "reason"],
    "SessionStopEventResult",
  );
  const promptType = results.BeforeAgentStartEventResult.fields["systemPrompt"]?.type;
  if (promptType !== "string[]") throw new ContractLockError(`systemPrompt element type changed: ${promptType ?? "missing"}`);

  return {
    bashInput: expandBashVariants(findNamedType(bashSource, "BashToolInput", checker), checker),
    eventNames,
    listeners: extractListeners(typesSource, checker),
    results,
    sessionStopContentUnion: extractContentUnion(sessionStopType, checker),
    sessionStopEvent: { fields: sessionStopFields },
  };
}
