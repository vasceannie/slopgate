import { afterEach, expect, test } from "bun:test";

import { buildContractSnapshot } from "./snapshot-builder.ts";
import { extractSessionStopResponse } from "./session-stop-text.ts";
import {
  buildBridgeSource,
  cleanupSyntheticRepos,
  createSyntheticRepo,
  incompatibleFieldFor,
  runVerifier,
} from "./verification-test-fixtures.ts";

const snapshot = await buildContractSnapshot();
const validAdapter = '_OMP_EVENT_ALIASES = {"input": "UserPromptSubmit"}\n';

afterEach(async () => {
  await cleanupSyntheticRepos();
});

test("accepts an adapter alias present in the locked event union", async () => {
  const repoRoot = await createSyntheticRepo({ adapterSource: validAdapter });
  const result = await runVerifier(repoRoot, "adapter");

  expect(result).toEqual({ exitCode: 0, stderr: "" });
}, 30000);

test("rejects an adapter alias absent from the locked event union", async () => {
  const repoRoot = await createSyntheticRepo({
    adapterSource: '_OMP_EVENT_ALIASES = {"not_an_omp_event": "UserPromptSubmit"}\n',
  });
  const result = await runVerifier(repoRoot, "adapter");

  expect(result).toEqual({
    exitCode: 1,
    stderr: expect.stringContaining('adapter event "not_an_omp_event" is absent from the snapshot'),
  });
}, 30000);

test("rejects a missing OMP adapter", async () => {
  const repoRoot = await createSyntheticRepo({});
  const result = await runVerifier(repoRoot, "adapter");

  expect(result).toEqual({
    exitCode: 1,
    stderr: expect.stringContaining("missing OMP adapter"),
  });
}, 30000);

test("rejects a dynamically constructed adapter alias map", async () => {
  const repoRoot = await createSyntheticRepo({
    adapterSource: '_OMP_EVENT_ALIASES = dict(input="UserPromptSubmit")\n',
  });
  const result = await runVerifier(repoRoot, "adapter");

  expect(result).toEqual({
    exitCode: 1,
    stderr: expect.stringContaining("must be a literal string-to-string dict"),
  });
}, 30000);

test("accepts a bridge whose listeners use their event-specific result fields", async () => {
  const repoRoot = await createSyntheticRepo({ bridgeSource: buildBridgeSource(snapshot) });
  const result = await runVerifier(repoRoot, "bridge");

  expect(result).toEqual({ exitCode: 0, stderr: "" });
}, 30000);

test("accepts a same-file helper with a statically resolvable return graph", async () => {
  const bridgeSource = buildBridgeSource(snapshot, {
    body: "return inputResult();",
    event: "input",
    prelude: "function inputResult() { return { handled: true }; }",
  });
  const repoRoot = await createSyntheticRepo({ bridgeSource });
  const result = await runVerifier(repoRoot, "bridge");

  expect(result).toEqual({ exitCode: 0, stderr: "" });
}, 30000);

test("accepts a nested same-file helper with a statically resolvable return graph", async () => {
  const bridgeSource = buildBridgeSource(snapshot, {
    body: "function inputResult() { return { handled: true }; } return inputResult();",
    event: "input",
  });
  const repoRoot = await createSyntheticRepo({ bridgeSource });
  const result = await runVerifier(repoRoot, "bridge");

  expect(result).toEqual({ exitCode: 0, stderr: "" });
}, 30000);

test("accepts adapter and bridge together in all mode", async () => {
  const repoRoot = await createSyntheticRepo({
    adapterSource: validAdapter,
    bridgeSource: buildBridgeSource(snapshot),
  });
  const result = await runVerifier(repoRoot, "all");

  expect(result).toEqual({ exitCode: 0, stderr: "" });
}, 30000);

test("rejects a missing OMP bridge", async () => {
  const repoRoot = await createSyntheticRepo({});
  const result = await runVerifier(repoRoot, "bridge");

  expect(result).toEqual({
    exitCode: 1,
    stderr: expect.stringContaining("missing OMP bridge"),
  });
}, 30000);

test("rejects a globally valid result field on the wrong event", async () => {
  const bridgeSource = buildBridgeSource(snapshot, {
    body: "return { block: true };",
    event: "input",
  });
  const repoRoot = await createSyntheticRepo({ bridgeSource });
  const result = await runVerifier(repoRoot, "bridge");

  expect(result).toEqual({
    exitCode: 1,
    stderr: expect.stringContaining('event "input" returns unsupported field "block"'),
  });
}, 30000);

const rejectedConstructions = [
  {
    body: "return missingResult();",
    name: "an unresolved helper call",
    prelude: "",
    reason: 'helper "missingResult" cannot be resolved in the bridge file',
  },
  {
    body: "return externalResult();",
    name: "an external helper call",
    prelude: 'import { externalResult } from "./external.ts";',
    reason: "external helper calls are not allowed in bridge return graphs",
  },
  {
    body: "return { ...base };",
    name: "a spread result",
    prelude: "const base = { handled: true };",
    reason: "spread properties are not allowed",
  },
  {
    body: 'return { ["handled"]: true };',
    name: "a computed result key",
    prelude: "",
    reason: "computed result keys are not allowed",
  },
  {
    body: "const result = {}; result.handled = true; return result;",
    name: "post-construction mutation",
    prelude: "",
    reason: "dynamically assembled result objects are not allowed",
  },
  {
    body: "const result = { handled: true }; return result;",
    name: "a dynamically assembled result object",
    prelude: "",
    reason: "dynamically assembled result objects are not allowed",
  },
] as const;

for (const testCase of rejectedConstructions) {
  test(`rejects ${testCase.name}`, async () => {
    const bridgeSource = buildBridgeSource(snapshot, {
      body: testCase.body,
      event: "input",
      prelude: testCase.prelude,
    });
    const repoRoot = await createSyntheticRepo({ bridgeSource });
    const result = await runVerifier(repoRoot, "bridge");

    expect(result).toEqual({ exitCode: 1, stderr: expect.stringContaining(testCase.reason) });
  }, 30000);
}

for (const [event, contract] of Object.entries(snapshot.listeners)) {
  const explicitVoid = contract.result_union.every((member) => member === "void");
  if (explicitVoid) {
    test(`rejects a non-void return from explicit-void event ${event}`, async () => {
      const bridgeSource = buildBridgeSource(snapshot, {
        body: "return { handled: true };",
        event,
      });
      const repoRoot = await createSyntheticRepo({ bridgeSource });
      const result = await runVerifier(repoRoot, "bridge");

      expect(result).toEqual({
        exitCode: 1,
        stderr: expect.stringContaining(`event "${event}" must return void`),
      });
    }, 30000);
    continue;
  }

  test(`rejects another event's result field from ${event}`, async () => {
    const incompatibleField = incompatibleFieldFor(snapshot, contract);
    const bridgeSource = buildBridgeSource(snapshot, {
      body: `return { ${JSON.stringify(incompatibleField)}: undefined };`,
      event,
    });
    const repoRoot = await createSyntheticRepo({ bridgeSource });
    const result = await runVerifier(repoRoot, "bridge");

    expect(result).toEqual({
      exitCode: 1,
      stderr: expect.stringContaining(
        `event "${event}" returns unsupported field "${incompatibleField}"`,
      ),
    });
  }, 30000);
}

const stopTextCases = [
  { expected: "", message: undefined, name: "absent assistant message" },
  { expected: "plain", message: { content: "plain" }, name: "string content" },
  {
    expected: "first\nsecond",
    message: {
      content: [
        { text: "first", type: "text" },
        { data: "ignored", type: "image" },
        { text: "second", type: "text" },
      ],
    },
    name: "mixed text array",
  },
  {
    expected: "",
    message: { content: [{ data: "ignored", type: "image" }] },
    name: "non-text content",
  },
] as const;

for (const testCase of stopTextCases) {
  test(`extracts canonical session-stop text for ${testCase.name}`, () => {
    expect(extractSessionStopResponse(testCase.message)).toBe(testCase.expected);
  }, 30000);
}

test("locks stop_hook_active on the session-stop input event", () => {
  expect(snapshot.session_stop.event.fields["stop_hook_active"]).toEqual({
    required: true,
    type: "false | true",
  });
}, 30000);

test("locks the session-stop response source to last_assistant_message", () => {
  expect(snapshot.session_stop_response_source).toBe("last_assistant_message");
}, 30000);

test("does not merge stop_hook_active into the session-stop result", () => {
  expect(snapshot.results.SessionStopEventResult.fields["stop_hook_active"]).toBeUndefined();
}, 30000);

test("locks the session-stop result independently from the input event", () => {
  expect(Object.keys(snapshot.results.SessionStopEventResult.fields).sort()).toEqual([
    "additionalContext",
    "continue",
    "decision",
    "reason",
  ]);
}, 30000);

test("does not permit action in the input result", () => {
  expect(snapshot.results.InputEventResult.fields["action"]).toBeUndefined();
}, 30000);
