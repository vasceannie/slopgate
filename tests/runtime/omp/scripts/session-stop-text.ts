import { ContractLockError, isRecord } from "./snapshot-schema.ts";

export function extractSessionStopResponse(message: unknown): string {
  if (!isRecord(message)) return "";
  const content = message["content"];
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";

  const textParts: string[] = [];
  for (const part of content) {
    if (isRecord(part) && part["type"] === "text" && typeof part["text"] === "string") {
      textParts.push(part["text"]);
    }
  }
  return textParts.join("\n");
}

export function assertCanonicalStopTextCases(): void {
  const cases: readonly { readonly expected: string; readonly message: unknown }[] = [
    { expected: "", message: undefined },
    { expected: "plain", message: { content: "plain" } },
    {
      expected: "first\nsecond",
      message: {
        content: [
          { text: "first", type: "text" },
          { data: "ignored", type: "image" },
          { text: "second", type: "text" },
        ],
      },
    },
    { expected: "", message: { content: [{ data: "ignored", type: "image" }] } },
  ];

  for (const testCase of cases) {
    if (extractSessionStopResponse(testCase.message) !== testCase.expected) {
      throw new ContractLockError("session_stop response extraction differs from the locked algorithm");
    }
  }
}
