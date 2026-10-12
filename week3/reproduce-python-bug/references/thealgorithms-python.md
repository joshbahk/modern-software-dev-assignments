# Testing TheAlgorithms/Python

Read the checkout's `AGENTS.md`, `CONTRIBUTING.md`, `pyproject.toml`, and
`.python-version`; these can change between revisions. Many algorithm files put
their tests directly in docstrings. Running a file as a script can instead launch
a benchmark or request interactive input, so inspect its `__main__` block first.

For a dependency-free module, set `module` to the identified repository-relative
file. For example, when investigating binary exponentiation:

```sh
module=maths/binary_exponentiation.py
python3 -B -m doctest -v "$module"
```

`-B` avoids creating bytecode files. Run a separate reproducer from the repository
root with `python3 -B -c '...'`. For a script saved outside the repository, use
`PYTHONPATH=. python3 -B /absolute/path/to/reproducer.py` from the repository root.
Import the target module; do not copy its implementation into the reproducer.

Do not install the entire project's scientific dependency set for an isolated
standard-library function. If the selected module needs dependencies or newer
syntax, use the project's supported environment. If that environment is unavailable,
report the setup limit. A dependency-free module that runs on an older interpreter
can provide a scoped observation, but does not establish compatibility with the
repository's required interpreter or verify its full suite.

The current contribution instructions distinguish algorithm changes from test-only
changes. Read the rules at the actual checkout before turning a diagnosis into a PR;
this skill's default output is a reproduction and recommendation.
