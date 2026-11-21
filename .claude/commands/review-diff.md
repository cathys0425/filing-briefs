---
description: First-pass review of the current branch by a fresh-context subagent
argument-hint: <requirement the change must satisfy> [base=<branch>]
---

Run a first-pass review of this branch using the `diff-reviewer` subagent.

Requirement and options: $ARGUMENTS

Steps:

1. Determine the base branch: the `base=` value if given, otherwise `main`.
2. Spawn the `diff-reviewer` subagent. Its prompt must contain only:
   - the requirement text above, verbatim
   - the instruction to review `git diff <base>...HEAD`
   Do not include your own summary of the change, your opinion of it, or anything from this conversation. The reviewer must not be anchored on the author's view.
3. Relay the reviewer's table unchanged. Do not fix anything unless asked.
4. End with this reminder of what the first pass does not cover:
   - Is this what was wanted?
   - Are the tests meaningful?
   - Does anything touch money or irreversible operations?
   - Spot-check adapter output against the raw vendor file.

If no requirement was given, ask for it instead of guessing one.
