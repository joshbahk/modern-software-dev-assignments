---
name: reproduce-python-bug
description: Reproduce and triage a reported wrong result or exception in a Python function before changing it. Use when asked to reproduce a bug, verify a bug report, or find a failing input in a Python repo. Do not use for code explanations or feature requests without a reported failure.
---

# Reproduce a Python bug

Turn a reported failure into a small executable example and decide whether it
violates the function's contract. A surprising result alone is not enough.

## Establish the case

From the repository root, record:

```sh
git rev-parse HEAD
git status --short
python3 --version
```

Read the repository's agent and contribution instructions, the relevant function,
its docstring, and its existing tests. Record the input, expected behavior, and
reported behavior. If a missing input or environment detail prevents reproduction,
ask for that specific detail instead of inventing it.

For TheAlgorithms/Python, read [the repository testing notes](references/thealgorithms-python.md)
before choosing a test command. For another repo, use its documented test runner.

## Reproduce before proposing a change

1. Run the narrow existing test set, then a separate example that calls the public
   function with the reported input. Record the command, output, and exit status.
   Passing existing tests does not disprove a new report.
2. Check the expected result independently: a hand calculation, a documented
   property, or a trusted implementation whose input domain matches this one.
   A library that supports more inputs is not automatically a valid oracle.
3. Reduce the example while preserving the same failure and staying inside the
   documented input domain. Keep a nearby passing case to show the boundary.
   If the report concerns a hang, use a bounded subprocess instead of letting
   the reproducer run indefinitely.
4. Test the most plausible competing explanation. For example, compare a boundary
   input with an ordinary input, or an allegedly failing input with a documented
   precondition. Do not change expected values just to make tests pass.

## Decide from the evidence

- **Confirmed defect:** a supported input contradicts the documented result or
  a justified invariant. Trace the smallest example through the relevant code and
  propose a narrow correction with a regression case.
- **Unsupported input:** the behavior follows an explicit precondition. Explain
  that restriction; do not widen the API just to match a different library.
- **Not reproduced:** the exact case behaves as specified at this revision.
  Report that result and identify which version or environment detail could matter.
- **Inconclusive:** setup failed, the contract is ambiguous, or the expected result
  has no reliable basis. Name what is missing. A failed import is not evidence of
  an algorithm defect. If execution is blocked, stop at the missing check; do not
  prescribe a code change from an unexecuted assumption.

Keep reproductions in a temporary location unless the user requests a repository
test. Propose fixes only after reproducing the problem; apply one only when the
task includes implementation. Do not silently alter unrelated local changes.

## Return a usable diagnosis

Give the classification first, followed by the repository revision and interpreter,
the smallest tested input and its contract status, expected versus actual behavior,
and a copyable reproduction command. Cite the relevant source lines. Separate
observed results from the proposed cause or fix. Report the inputs actually tested;
matching a few controls does not establish correctness for every valid input.
State which checks ran and their limits; do not claim a full suite passed after
testing one module. End with the next concrete step.
