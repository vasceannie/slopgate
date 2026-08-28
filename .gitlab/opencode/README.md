# OpenCode merge-request review

This repository uses the `opencode-review` GitLab CI job for an additional, read-only MR review. It is separate from the shared PR-Agent webhook.

## Run a review

1. In GitLab, open **Build > Pipelines > New pipeline**.
2. Select the protected default branch (`master`).
3. Add `OPENCODE_MR_IID` with the numeric merge-request IID.
4. Run the pipeline.

The job fetches the MR head, computes its merge base with the default-branch commit, and stores both the raw JSONL and rendered review as pipeline artifacts. It cannot edit the checkout or post to GitLab.

`OPENCODE_AUTH_JSON` is a protected, masked, hidden, file-type project variable. Do not replace it with a plain environment variable or commit credentials to this directory.

## PR-Agent

The shared PR-Agent webhook handles normal MR events. To request a review from a comment, begin the comment with `/review`; an optional `@agent-mr` mention can follow the command. Published review notes are authored by the dedicated `agent-mr` GitLab user.
