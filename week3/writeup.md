# Week 3 Write-up

**Skill name**, and the repo you targeted:
> [reproduce-python-bug](reproduce-python-bug/SKILL.md), targeting [TheAlgorithms/Python](https://github.com/TheAlgorithms/Python).


## Part I: The Workflow

**What the workflow is**, and why it's worth encoding:
> The workflow checks whether a reported bug is actually a bug before suggesting a fix. It reads what the function promises to do, runs the existing tests, and tries a small example of the problem. I chose this because I want the agent to verify the problem before it starts changing code.

**The decision point** in it (what the agent has to judge, not just execute):
> The main decision is whether the function is supposed to support the input. For example, `binary_exp_mod_recursive` explicitly rejects negative exponents, even though Python's `pow` can handle some of them. That difference isn't a bug. However, a zero exponent and a modulus of one are allowed, so returning the wrong remainder for that input is a bug.

**What you learned running it manually** that you would not have guessed:
> I ran the workflow manually before writing the skill. All 26 existing doctests in `maths/binary_exponentiation.py` passed, but both modular exponentiation functions returned `1` for `(3, 0, 1)`, when `(3 ** 0) % 1` is `0`. Reducing the base to `1` kept the failure. The tests covered invalid inputs but missed this valid combination, which showed why the skill needs a separate reproduction even when existing tests pass.


## Part II: The Skill

**Your description**, verbatim:
```
Reproduce and triage a reported wrong result or exception in a Python function before changing it. Use when asked to reproduce a bug, verify a bug report, or find a failing input in a Python repo. Do not use for code explanations or feature requests without a reported failure.
```

**Why it's worded that way** (what a user would type to trigger it):
> The description uses 'reproduce a bug,' 'verify a bug report,' and 'wrong result' because a user can ask for those things without knowing the skill's name. It excludes code explanations so that asking how a function works doesn't start a debugging task.

**Judgment encoded in the body** (what it says to do when things are ambiguous, and what not to do):
> The skill distinguishes a confirmed bug, unsupported input, a report it can't reproduce, and an inconclusive result. It says to check that an input is valid for both implementations before comparing them, and to stop if a missing detail or blocked test prevents a diagnosis. After Claude incorrectly claimed the results always matched `pow` for nonnegative exponents, I added a rule to limit claims to the inputs actually tested. It also says to propose a fix only after reproducing the problem, and apply one only if asked.

**Supporting files**, if any, and why they aren't inline:

| File | Contents | Why it's separate |
|---|---|---|
| `references/thealgorithms-python.md` | Test commands, imports, and Python version/dependency guidance. | These details only apply to TheAlgorithms/Python, so they don't need to load for other repos. |


## Part III: Testing

**Triggering:**

| Prompt | Should fire? | Did it? |
|---|---|---|
| In maths/binary_exponentiation.py, binary_exp_mod_recursive(3, 0, 1) returns 1, but I expected 0. Reproduce this and find a small failing case before suggesting a fix. Keep the repo unchanged. | Yes | Yes. Called `reproduce-python-bug`. |
| I think binary_exp_mod_recursive(3, -1, 7) is broken because it raises ValueError instead of returning 5 like pow does. Can you check whether this is actually a bug? Keep the repo unchanged. | Yes | Yes. Called `reproduce-python-bug`. |
| Someone reported that interpolation_search_by_recursion([], 1) crashes in searches/interpolation_search.py. Verify the report against this checkout and give me a reproducible diagnosis before changing anything. | Yes | Yes. Called `reproduce-python-bug`. |
| Explain how binary_exp_mod_recursive in maths/binary_exponentiation.py works. Walk me through the normal example (3, 4, 5). Keep the repo unchanged. | No (near-miss) | No. No `Skill` call. |

**End-to-end run** on your repo, and the result:
> I ran the first prompt above in a fresh Claude Code session. The commands and transcript are in [test-evidence.md](test-evidence.md).

```text
Client: Claude Code 2.1.283
Commit: f6b39e1a6c461001c9ca8af78ba828a27d282ccb
Interpreter: Python 3.14.3

Claude called Skill with {"skill": "reproduce-python-bug"}, then ran the
module's doctests and a separate reproduction.

Results summarized from the tool output:
Input       Recursive  Iterative  pow
(3, 0, 1)   1          1          0
(3, 0, 2)   1          1          1
(3, 1, 1)   0          0          0

Claude confirmed the bug in both implementations. The recursive base case
returns 1 without applying the modulus. The iterative version starts at 1
and skips the loop when the exponent is zero. It proposed reducing those
values modulo the modulus; no fix was applied.

The run also missed a step: Claude skipped AGENTS.md and CONTRIBUTING.md,
then incorrectly said code and doctest changes should go in the same PR.
The repository instructions say to keep them separate.

These checks covered selected modules on Python 3.14.3. The repo requests
Python 3.15t, so this does not verify that environment or the full suite.
```


## Submission
1. `Command (⌘) + F` for `TODO`. No results means you're done.
2. Confirm the skill directory itself is committed under `week3/`.
3. Push all changes to your remote repository and submit via Gradescope.
