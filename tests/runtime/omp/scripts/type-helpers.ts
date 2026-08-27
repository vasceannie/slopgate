import * as ts from "typescript";

import { ContractLockError, type FieldSchema } from "./snapshot-schema.ts";

const TYPE_FORMAT_FLAGS = ts.TypeFormatFlags.NoTruncation | ts.TypeFormatFlags.UseAliasDefinedOutsideCurrentScope;

export function createDeclarationProgram(rootNames: readonly string[]): ts.Program {
  const program = ts.createProgram({
    rootNames: [...rootNames],
    options: {
      module: ts.ModuleKind.NodeNext,
      moduleResolution: ts.ModuleResolutionKind.NodeNext,
      noEmit: true,
      skipLibCheck: true,
      target: ts.ScriptTarget.ESNext,
    },
  });
  const diagnostics = [...program.getSyntacticDiagnostics(), ...program.getSemanticDiagnostics()];
  if (diagnostics.length > 0) {
    const first = diagnostics[0];
    const message = first ? ts.flattenDiagnosticMessageText(first.messageText, " ") : "unknown diagnostic";
    throw new ContractLockError(`declaration program failed: ${message}`);
  }
  return program;
}

export function requireSource(program: ts.Program, path: string): ts.SourceFile {
  const source = program.getSourceFile(path);
  if (!source) throw new ContractLockError(`missing declaration source: ${path}`);
  return source;
}

export function findNamedType(source: ts.SourceFile, name: string, checker: ts.TypeChecker): ts.Type {
  for (const statement of source.statements) {
    if ((ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement)) && statement.name.text === name) {
      return checker.getTypeAtLocation(statement.name);
    }
  }
  throw new ContractLockError(`missing type declaration: ${name}`);
}

export function nonUndefinedTypes(type: ts.Type): readonly ts.Type[] {
  const members = type.isUnion() ? type.types : [type];
  return members.filter((member) => (member.flags & ts.TypeFlags.Undefined) === 0);
}

export function canonicalType(type: ts.Type, checker: ts.TypeChecker, location: ts.Node): string {
  return nonUndefinedTypes(type)
    .map((member) => checker.typeToString(member, location, TYPE_FORMAT_FLAGS))
    .sort()
    .join(" | ");
}

export function fieldsForType(type: ts.Type, checker: ts.TypeChecker): Readonly<Record<string, FieldSchema>> {
  const fields: Record<string, FieldSchema> = {};
  const properties = checker.getPropertiesOfType(type).sort((left, right) => left.name.localeCompare(right.name));
  for (const symbol of properties) {
    const declaration = symbol.valueDeclaration ?? symbol.declarations?.[0];
    if (!declaration) throw new ContractLockError(`missing declaration for field: ${symbol.name}`);
    fields[symbol.name] = {
      required: (symbol.flags & ts.SymbolFlags.Optional) === 0,
      type: canonicalType(checker.getTypeOfSymbolAtLocation(symbol, declaration), checker, declaration),
    };
  }
  return fields;
}

export function extractEventNames(extensionEvent: ts.Type, checker: ts.TypeChecker): readonly string[] {
  const names = new Set<string>();
  for (const eventType of nonUndefinedTypes(extensionEvent)) {
    const typeProperty = checker.getPropertyOfType(eventType, "type");
    const declaration = typeProperty?.valueDeclaration ?? typeProperty?.declarations?.[0];
    if (!typeProperty || !declaration) throw new ContractLockError("event union member lacks a type discriminator");
    const discriminator = checker.getTypeOfSymbolAtLocation(typeProperty, declaration);
    if (!discriminator.isStringLiteral()) throw new ContractLockError("event discriminator is not a string literal");
    names.add(discriminator.value);
  }
  return [...names].sort();
}

export function extractContentUnion(sessionStopEvent: ts.Type, checker: ts.TypeChecker): readonly string[] {
  const field = checker.getPropertyOfType(sessionStopEvent, "last_assistant_message");
  const declaration = field?.valueDeclaration ?? field?.declarations?.[0];
  if (!field || !declaration) throw new ContractLockError("SessionStopEvent lacks last_assistant_message");
  const contentTypes = new Set<string>();
  for (const messageType of nonUndefinedTypes(checker.getTypeOfSymbolAtLocation(field, declaration))) {
    const content = checker.getPropertyOfType(messageType, "content");
    const contentDeclaration = content?.valueDeclaration ?? content?.declarations?.[0];
    if (!content || !contentDeclaration) continue;
    const contentType = checker.getTypeOfSymbolAtLocation(content, contentDeclaration);
    for (const member of nonUndefinedTypes(contentType)) {
      contentTypes.add(checker.typeToString(member, contentDeclaration, TYPE_FORMAT_FLAGS));
    }
  }
  const result = [...contentTypes].sort();
  if (!result.includes("string") || !result.some((value) => value.includes("TextContent"))) {
    throw new ContractLockError("AgentMessage content union lacks string and text-array shapes");
  }
  return result;
}
