import { existsSync } from "node:fs";
import { join } from "node:path";

import * as ts from "typescript";

import {
  analyzeReturnGraph,
  resolveBridgeCallback,
  type BridgeAnalysisContext,
} from "./bridge-return-analysis.ts";
import {
  ContractLockError,
  type ContractSnapshot,
  type ListenerContract,
} from "./snapshot-schema.ts";

type Registration = {
  readonly callback: ts.Expression;
  readonly event: string;
};

export function verifyBridge(repoRoot: string, snapshot: ContractSnapshot): void {
  const bridgePath = join(repoRoot, "src", "slopgate", "resources", "omp_extension.ts");
  if (!existsSync(bridgePath)) throw new ContractLockError(`missing OMP bridge: ${bridgePath}`);

  const program = createBridgeProgram(bridgePath);
  const source = program.getSourceFile(bridgePath);
  if (!source) throw new ContractLockError(`failed to load OMP bridge source: ${bridgePath}`);
  assertSyntacticallyValid(program, source);
  const context: BridgeAnalysisContext = { checker: program.getTypeChecker(), source };
  const registrations = collectRegistrations(source);
  const listeners = new Map<string, ListenerContract>(Object.entries(snapshot.listeners));

  for (const registration of registrations.values()) {
    const contract = listeners.get(registration.event);
    if (!contract) {
      throw new ContractLockError(
        `bridge registers event "${registration.event}" outside the snapshot listener inventory`,
      );
    }
    const callback = resolveBridgeCallback(registration.callback, context, registration.event);
    verifyReturnShapes(registration.event, contract, analyzeReturnGraph(callback, context));
  }

  for (const event of listeners.keys()) {
    if (!registrations.has(event)) {
      throw new ContractLockError(`bridge is missing required listener "${event}"`);
    }
  }
}

function createBridgeProgram(bridgePath: string): ts.Program {
  return ts.createProgram({
    rootNames: [bridgePath],
    options: {
      module: ts.ModuleKind.NodeNext,
      moduleResolution: ts.ModuleResolutionKind.NodeNext,
      noEmit: true,
      noResolve: true,
      target: ts.ScriptTarget.ESNext,
    },
  });
}

function collectRegistrations(source: ts.SourceFile): ReadonlyMap<string, Registration> {
  const registrations = new Map<string, Registration>();
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && isPiOnCall(node.expression)) {
      const eventArgument = node.arguments[0];
      const callback = node.arguments[1];
      if (!eventArgument || !ts.isStringLiteral(eventArgument)) {
        throw new ContractLockError("bridge listener event must be a string literal");
      }
      if (!callback) throw new ContractLockError(`bridge listener "${eventArgument.text}" has no callback`);
      if (registrations.has(eventArgument.text)) {
        throw new ContractLockError(`bridge registers duplicate listener "${eventArgument.text}"`);
      }
      registrations.set(eventArgument.text, { callback, event: eventArgument.text });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return registrations;
}

function isPiOnCall(expression: ts.LeftHandSideExpression): boolean {
  return ts.isPropertyAccessExpression(expression)
    && ts.isIdentifier(expression.expression)
    && expression.expression.text === "pi"
    && expression.name.text === "on";
}

function verifyReturnShapes(
  event: string,
  contract: ListenerContract,
  shapes: ReturnType<typeof analyzeReturnGraph>,
): void {
  const explicitVoid = contract.result_union.every((member) => member === "void");
  const allowedFields = new Set(Object.keys(contract.fields));
  for (const shape of shapes) {
    if (shape.kind === "void") continue;
    if (explicitVoid) throw new ContractLockError(`event "${event}" must return void`);
    for (const field of shape.fields) {
      if (!allowedFields.has(field)) {
        throw new ContractLockError(`event "${event}" returns unsupported field "${field}"`);
      }
    }
  }
}

function assertSyntacticallyValid(program: ts.Program, source: ts.SourceFile): void {
  const diagnostic = program
    .getSyntacticDiagnostics(source)
    .find((item) => item.category === ts.DiagnosticCategory.Error);
  if (diagnostic) {
    throw new ContractLockError(
      `bridge TypeScript syntax error: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, " ")}`,
    );
  }
}
