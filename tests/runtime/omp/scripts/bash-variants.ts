import * as ts from "typescript";

import {
  ContractLockError,
  type BashInputContract,
  type PrimitiveType,
} from "./snapshot-schema.ts";
import { nonUndefinedTypes } from "./type-helpers.ts";

function primitiveType(type: ts.Type, checker: ts.TypeChecker): PrimitiveType {
  const primitives = new Set<PrimitiveType>();
  for (const member of nonUndefinedTypes(type)) {
    if ((member.flags & ts.TypeFlags.StringLike) !== 0) primitives.add("string");
    else if ((member.flags & ts.TypeFlags.NumberLike) !== 0) primitives.add("number");
    else if ((member.flags & ts.TypeFlags.BooleanLike) !== 0) primitives.add("boolean");
    else if (checker.isArrayType(member) || checker.isTupleType(member)) primitives.add("array");
    else if ((member.flags & ts.TypeFlags.Object) !== 0) primitives.add("object");
    else throw new ContractLockError(`unsupported bash field type: ${checker.typeToString(member)}`);
  }
  if (primitives.size !== 1) throw new ContractLockError("bash field has a non-primitive union");
  const value = primitives.values().next().value;
  if (!value) throw new ContractLockError("bash field has no concrete type");
  return value;
}

function orderedRecord<T>(entries: readonly (readonly [string, T])[]): Record<string, T> {
  const result: Record<string, T> = {};
  for (const [key, value] of [...entries].sort(([left], [right]) => left.localeCompare(right))) {
    result[key] = value;
  }
  return result;
}

export function expandBashVariants(type: ts.Type, checker: ts.TypeChecker): BashInputContract {
  const variants = new Map<string, Readonly<Record<string, PrimitiveType>>>();
  const fieldTypes: Record<string, PrimitiveType> = {};

  for (const branch of nonUndefinedTypes(type)) {
    if ((branch.flags & ts.TypeFlags.Object) === 0) throw new ContractLockError("bash input branch is not an object");
    if (checker.getIndexInfosOfType(branch).length > 0) throw new ContractLockError("bash input has an index signature");
    const required: Array<readonly [string, PrimitiveType]> = [];
    const optional: Array<readonly [string, PrimitiveType]> = [];
    for (const symbol of checker.getPropertiesOfType(branch).sort((left, right) => left.name.localeCompare(right.name))) {
      const declaration = symbol.valueDeclaration ?? symbol.declarations?.[0];
      if (!declaration) throw new ContractLockError(`missing declaration for bash field: ${symbol.name}`);
      const primitive = primitiveType(checker.getTypeOfSymbolAtLocation(symbol, declaration), checker);
      const previous = fieldTypes[symbol.name];
      if (previous && previous !== primitive) throw new ContractLockError(`bash field changes type: ${symbol.name}`);
      fieldTypes[symbol.name] = primitive;
      ((symbol.flags & ts.SymbolFlags.Optional) === 0 ? required : optional).push([symbol.name, primitive]);
    }

    for (let mask = 0; mask < 2 ** optional.length; mask += 1) {
      const entries = [...required];
      optional.forEach((entry, index) => {
        if ((mask & 2 ** index) !== 0) entries.push(entry);
      });
      const variant = orderedRecord(entries);
      variants.set(JSON.stringify(variant), variant);
    }
  }

  const sortedVariants = [...variants.values()].sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
  const allKeys = Object.keys(fieldTypes).sort();
  const requiredKeys = allKeys.filter((key) => sortedVariants.every((variant) => key in variant));
  return {
    field_types: orderedRecord(Object.entries(fieldTypes)),
    optional_keys: allKeys.filter((key) => !requiredKeys.includes(key)),
    required_keys: requiredKeys,
    source: "BashToolInput",
    variants: sortedVariants,
  };
}
