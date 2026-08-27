import * as ts from "typescript";

import { ContractLockError } from "./snapshot-schema.ts";

type BridgeFunction = ts.ArrowFunction | ts.FunctionDeclaration | ts.FunctionExpression;

export type BridgeAnalysisContext = {
  readonly checker: ts.TypeChecker;
  readonly source: ts.SourceFile;
};

export type ReturnShape =
  | { readonly kind: "object"; readonly fields: readonly string[] }
  | { readonly kind: "void" };

export function resolveBridgeCallback(
  expression: ts.Expression,
  context: BridgeAnalysisContext,
  event: string,
): BridgeFunction {
  const callback = unwrapParentheses(expression);
  if (ts.isArrowFunction(callback) || ts.isFunctionExpression(callback)) return callback;
  if (ts.isIdentifier(callback)) return resolveLocalFunction(callback, context, `callback for event "${event}"`);
  throw new ContractLockError(`callback for event "${event}" cannot be resolved in the bridge file`);
}

export function analyzeReturnGraph(
  callback: BridgeFunction,
  context: BridgeAnalysisContext,
): readonly ReturnShape[] {
  return analyzeFunction(callback, context, new Set<BridgeFunction>());
}

function analyzeFunction(
  callback: BridgeFunction,
  context: BridgeAnalysisContext,
  active: ReadonlySet<BridgeFunction>,
): readonly ReturnShape[] {
  if (active.has(callback)) throw new ContractLockError("helper return graph contains a cycle");
  if (!callback.body) throw new ContractLockError("bridge helper has no implementation body");

  const nextActive = new Set(active);
  nextActive.add(callback);
  if (!ts.isBlock(callback.body)) {
    return analyzeExpression(callback.body, context, nextActive);
  }

  const returns = collectReturns(callback.body);
  if (returns.length === 0) return [{ kind: "void" }];
  return returns.flatMap((statement) => {
    if (!statement.expression) return [{ kind: "void" }];
    return analyzeExpression(statement.expression, context, nextActive);
  });
}

function analyzeExpression(
  expression: ts.Expression,
  context: BridgeAnalysisContext,
  active: ReadonlySet<BridgeFunction>,
): readonly ReturnShape[] {
  const resolved = unwrapReturnExpression(expression);
  if (ts.isIdentifier(resolved)) {
    if (resolved.text === "undefined") return [{ kind: "void" }];
    throw new ContractLockError("dynamically assembled result objects are not allowed");
  }
  if (ts.isObjectLiteralExpression(resolved)) return [objectReturnShape(resolved)];
  if (ts.isConditionalExpression(resolved)) {
    return [
      ...analyzeExpression(resolved.whenTrue, context, active),
      ...analyzeExpression(resolved.whenFalse, context, active),
    ];
  }
  if (ts.isCallExpression(resolved)) {
    const callee = unwrapParentheses(resolved.expression);
    if (!ts.isIdentifier(callee)) {
      throw new ContractLockError("external helper calls are not allowed in bridge return graphs");
    }
    const helper = resolveLocalFunction(callee, context, `helper "${callee.text}"`);
    return analyzeFunction(helper, context, active);
  }
  throw new ContractLockError("dynamically assembled result objects are not allowed");
}

function resolveLocalFunction(
  identifier: ts.Identifier,
  context: BridgeAnalysisContext,
  label: string,
): BridgeFunction {
  const symbol = context.checker.getSymbolAtLocation(identifier);
  if (!symbol) throw new ContractLockError(`${label} cannot be resolved in the bridge file`);
  if ((symbol.flags & ts.SymbolFlags.Alias) !== 0) {
    throw new ContractLockError("external helper calls are not allowed in bridge return graphs");
  }

  for (const declaration of symbol.declarations ?? []) {
    if (declaration.getSourceFile() !== context.source) continue;
    if (ts.isFunctionDeclaration(declaration) && declaration.body) return declaration;
    if (!ts.isVariableDeclaration(declaration) || !declaration.initializer) continue;
    const initializer = unwrapParentheses(declaration.initializer);
    if (ts.isArrowFunction(initializer) || ts.isFunctionExpression(initializer)) return initializer;
  }
  throw new ContractLockError(`${label} cannot be resolved in the bridge file`);
}

function objectReturnShape(objectLiteral: ts.ObjectLiteralExpression): ReturnShape {
  const fields = new Set<string>();
  for (const property of objectLiteral.properties) {
    if (ts.isSpreadAssignment(property)) {
      throw new ContractLockError("spread properties are not allowed in bridge results");
    }
    if (!ts.isPropertyAssignment(property) && !ts.isShorthandPropertyAssignment(property)) {
      throw new ContractLockError("bridge result objects may contain only data properties");
    }
    if (ts.isComputedPropertyName(property.name)) {
      throw new ContractLockError("computed result keys are not allowed");
    }
    const field = propertyName(property.name);
    if (fields.has(field)) throw new ContractLockError(`duplicate bridge result field "${field}"`);
    fields.add(field);
  }
  return { fields: [...fields].sort(), kind: "object" };
}

function propertyName(name: ts.PropertyName): string {
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) return name.text;
  throw new ContractLockError("bridge result contains an unsupported property name");
}

function collectReturns(body: ts.Block): readonly ts.ReturnStatement[] {
  const returns: ts.ReturnStatement[] = [];
  const visit = (node: ts.Node): void => {
    for (const child of node.getChildren()) {
      if (isNestedScope(child)) continue;
      if (ts.isReturnStatement(child)) {
        returns.push(child);
        continue;
      }
      visit(child);
    }
  };
  visit(body);
  return returns;
}

function isNestedScope(node: ts.Node): boolean {
  return ts.isArrowFunction(node)
    || ts.isFunctionDeclaration(node)
    || ts.isFunctionExpression(node)
    || ts.isMethodDeclaration(node)
    || ts.isGetAccessorDeclaration(node)
    || ts.isSetAccessorDeclaration(node)
    || ts.isConstructorDeclaration(node)
    || ts.isClassDeclaration(node)
    || ts.isClassExpression(node);
}

function unwrapParentheses(expression: ts.Expression): ts.Expression {
  let current = expression;
  while (ts.isParenthesizedExpression(current)) current = current.expression;
  return current;
}

function unwrapReturnExpression(expression: ts.Expression): ts.Expression {
  let current = unwrapParentheses(expression);
  while (ts.isAwaitExpression(current)) current = unwrapParentheses(current.expression);
  return current;
}
