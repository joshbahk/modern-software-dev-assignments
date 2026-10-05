# Week 1 Write-up

## Part I: Capture

**Setup** (enough for a reader to reproduce your capture):
```
claude --version:  2.1.274 (Claude Code)
mitmproxy version: Mitmproxy: 12.2.3 binary
proxy command:     mitmweb --listen-host 127.0.0.1 --listen-port 58888 \
        --web-open-browser --mode reverse:https://api.anthropic.com \
        -w session.flows
settings file:     .claude/settings.json
    {
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:58888",
    "ENABLE_TOOL_SEARCH": "true"
  }
}
```

**The session.** What task, against what repo, and how many `POST /v1/messages` requests did it produce?
> I had Claude Code create a simple calculator app in a separate repo called calculator-scratch. Then, I deleted two functions in two different files, which broke many tests. I asked Claude Code to fix the issue by making a clear plan. It confirmed that the program was broken; in fact, 0 tests ran instead of the previous 16 that had passed. It asked me how to fix, and I had it make targeted edits, which edited the two files, made fixes, and eventually led to the tests passing. For the fixing process, 27 requests were produced.

| Requirement | Evidence |
|---|---|
| Touched ≥ 2 files | "role": "user",
            "content": [
                {
                    "tool_use_id": "toolu_0151rtjuKbNynwVsPb3LDx4U",
                    "type": "tool_result",
                    "content": "The file /Users/joshbahk/Documents/GitHub/calculator-scratch/calculator/core.py has been updated successfully. (file state is current in your context — no need to Read it back)"
                }
            ] 
            "role": "user",
            "content": [
                {
                    "tool_use_id": "toolu_01NkhNtcDaF2iSAmwTELDjWC",
                    "type": "tool_result",
                    "content": "The file /Users/joshbahk/Documents/GitHub/calculator-scratch/calculator/app.py has been updated successfully. (file state is current in your context — no need to Read it back)"
                }
            ]
            |
| Failed at least once | "role": "user",
            "content": [
                {
                    "tool_use_id": "toolu_01Namky7PacbhiH4wTF98tH3",
                    "type": "tool_result",
                    "content": "============================= test session starts ==============================\nplatform darwin -- Python 3.13.11, pytest-9.0.3, pluggy-1.5.0 -- /opt/miniconda3/bin/python\ncachedir: .pytest_cache\nrootdir: /Users/joshbahk/Documents/GitHub/calculator-scratch\nconfigfile: pyproject.toml\ntestpaths: tests\nplugins: anyio-4.13.0\ncollecting ... collected 0 items / 2 errors\n\n==================================== ERRORS ====================================\n______________________ ERROR collecting tests/test_api.py ______________________\ntests/test_api.py:4: in <module>\n    from calculator.app import app\ncalculator/app.py:10: in <module>\n    from calculator.core import compute\ncalculator/core.py:23: in <module>\n    \"subtract\": subtract,\n                ^^^^^^^^\nE   NameError: name 'subtract' is not defined\n_____________________ ERROR collecting tests/test_core.py ______________________\ntests/test_core.py:3: in <module>\n    from calculator.core import add, compute, divide, multiply, subtract\ncalculator/core.py:23: in <module>\n    \"subtract\": subtract,\n                ^^^^^^^^\nE   NameError: name 'subtract' is not defined\n=============================== warnings summary ===============================\n../../../../../opt/miniconda3/lib/python3.13/site-packages/fastapi/testclient.py:1\n  /opt/miniconda3/lib/python3.13/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.\n    from starlette.testclient import TestClient as TestClient  # noqa\n\n-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html\n=========================== short test summary info ============================\nERROR tests/test_api.py - NameError: name 'subtract' is not defined\nERROR tests/test_core.py - NameError: name 'subtract' is not defined\n!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!!\n========================= 1 warning, 2 errors in 0.27s =========================\nShell cwd was reset to /Users/joshbahk/Documents/GitHub/modern-software-dev-assignments",
                    "is_error": false
                }
            ] |
| Long enough to plan | {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": "Entered plan mode. You should now focus on exploring the codebase and designing an implementation approach.\n\nIn plan mode, you should:\n1. Thoroughly explore the codebase to understand existing patterns\n2. Identify similar features and architectural approaches\n3. Consider multiple approaches and their trade-offs\n4. Use AskUserQuestion if you need to clarify the approach\n5. Design a concrete implementation strategy\n6. When ready, use ExitPlanMode to present your plan for approval\n\nRemember: DO NOT write or edit any files yet. This is a read-only exploration and planning phase.",
                    "tool_use_id": "toolu_01Np1FYHNEFq8qj1spkRUtX1"
                }
            ]
        } |
| Your own repo | "role": "user",
            "content": [
                {
                    "tool_use_id": "toolu_01KzYL83mnMc7Mzi7nRNJyqo",
                    "type": "tool_result",
                    "content": "=== log ===\n82a9eff Simple two-operand calculator with FastAPI and a static UI\n=== status ===\n(clean if nothing above)\n=== tracked files ===\n.gitignore\nREADME.md\ncalculator/__init__.py\ncalculator/app.py\ncalculator/core.py\ncalculator/static/app.js\ncalculator/static/index.html\npyproject.toml\ntests/test_api.py\ntests/test_core.py\nShell cwd was reset to /Users/joshbahk/Documents/GitHub/modern-software-dev-assignments",
                    "is_error": false
                }
            ] |

**What you redacted** from the excerpts quoted below, and why:
> Nothing redacted.


## Part II: System Prompt Annotation

**a. Structure.** Major sections in order, one line each on what it does, and why this order.
> The first section gives information on the Claude Code version and the fact that I am using the command line interface. The second section gives a message to Claude Code stating its identity: "You are Claude Code, Anthropic's official CLI for Claude". The third section is significantly longer, giving the full system prompt which includes many messages intended for safety reasons. This ordering makes sense because it provides the clear technical information of versions and identity early, before going into a much deeper dive on specific instructions.

**b. Tone and verbosity.** Quote the controlling instructions, then say what failure mode they defend against.
```
Avoid unnecessary or excessive self-correction. Only correct an earlier statement in your user-facing text when the error would change the user's code, conclusions, or decisions
```
> This isntruction helps stop Claude from contradicting itself for user-facing responses, which can be really confusing to parse through as a user.

**c. When not to act.** Quote the destructive-operation gates, scope limits, or refusal conditions, and what each buys.
```
Refuse requests for destructive techniques, DoS attacks, mass targeting, supply chain compromise, or detection evasion for malicious purposes. 
```
> This helps to ensure that Claude will not be used for malicious purposes like DoS attacks, which would be bad for Anthropic's PR if it was allowed to do so.

**d. Environment context.** What the agent is told about machine/repo/session, and where it lives in the request (`system` field or a `role: "system"` message).
> The environment context is given in a role: "system" and is told the primary working directory, that it is a git repo, and the platform, shell, OS version, scratchpad directory, etc.

**e. `<system-reminder>`.** Where they appear (cite an example), two distinct purposes you can evidence, and why they are injected mid-conversation rather than stated once.
```
"text": "<system-reminder>\nAs you answer the user's questions, you can use the following context:\n# userEmail\nThe user's email address is [REDACTED: email address]. Use it only to identify the user, such as for authorship, attribution, or filtering their own work. Never send it to an unrelated service, such as in a request header, URL, or payload, unless the user explicitly asks.\n# gitStatus\nThis is the git status at the start of the conversation. Note that this status is a snapshot in time, and will not update during the conversation.\n\nCurrent branch: master\n\nMain branch (you will usually use this for PRs): master\n\nGit user: joshbahk\n\nStatus:\n?? .claude/\n?? session.flows\n\nRecent commits:\n90a2fbb Week 1 Assignment\nca2df55 edit assignment.md\nb8be3a2 week8\n45d3878 graphite set up\n7c92309 week7\n\nIMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.\n</system-reminder>"
```
> The system reminder has the purpose of giving extra information to the model (like my email address) and also for safety reasons (like not sending my email address to an unrelated service). It's injected mid-conversation in order to ensure that this information is kept and the model continues to understand it even when context is large.


## Part III: Tool Design Annotation

**Inventory.** Did the set change across requests? If so, what triggered it?

| Built-in | MCP | Deferred | **Total** | Changed mid-session? |
|---|---|---|---|---|
| 33 | 42 | 60 | 75 | Yes, it grew when ToolSearch entered EnterPlanMode |

**Two tools.** Pick tools that differ from each other.

| | Tool 1 | Tool 2 |
|---|---|---|
| Name | Edit | EnterPlanMode |
| Key schema fields | properties: {"file_path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}, "replace_all": {"type": "boolean", "default": false}} | {"type": "object", "properties": {}, "additionalProperties": false} |
| Required vs. optional vs. not exposed, and why | Required: file_path, old_string, new_string. Optional: replace_all. It makes sense that you need the file path, old, and new, when editing a file (it would be hard to edit without it). Replace_all seems like it should be optional beacuse you don't always need to replace every instance of the old string, but it can be nice to if you need to edit a lot at once. | No required/optional fields. This makes sense because EnterPlanMode essentially should function like a boolean toggle; either you enter or you don't. No fields really needed. |
| Description is defending against… (quote + the wrong behavior) | "You must Read the file in this conversation before editing, or the call will fail." This defends against Claude Code editing a file without being sure of what is even in it (which could lead to many sorts of errors) | "Getting user sign-off on your approach before writing code prevents wasted effort and ensures alignment" This helps to make sure that, when planning, the user has the opportunity to review the plan before Claude writes a bunch of code, wasting tokens. |
| Deliberately does *not* do… and what that implies | It deliberately does not do anything other than basic string replacement in a file. It doesn't let you do a bunch of files at once or run code separately, which implies that this is meant to be a minimal interface for Claude to edit files. | There is no writing of a plan here, just triggering the start of the plan mode, which is deliberate and allows for the EnterPlanMode to essentially just be used as a toggle, without overcomplicating. |

Why these two?
> I chose these two, because, as the assignment description stated, these are very different tools. The Edit tool has parameters and takes action on user files, while the EnterPlanMode tool is very minimal and is used for orchestration purposes (essentially just a toggle).


## Part IV: Behavioral Analysis

**Every answer must be labeled `[OBSERVED]` or `[INFERRED]` and cite its evidence. Unlabeled answers earn no credit.**

**a. Error recovery**: `[OBSERVED]` · evidence: `I saw a failure when Claude attempted to use the Edit tool`

What the agent saw, verbatim:
```
"role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "content": "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>",
                    "is_error": true,
                    "tool_use_id": "toolu_01YASHZQXkT6Z2z2hUvNWeT7"
                }
            ]
```
What it tried next, and turns to recover:
> Claude tried to use the Read tool on core.py and app.py, and then it tried the Edit tool again, which was a success.

**b. Planning**: `[INFERRED]` · evidence: `Claude told me that it entered Plan mode and began the planning process.`
> Claude planned both using a tool (EnterPlanMode) but also it was a result of the prompt instruction, and also probably an emergent behavior of Claude's own training and decisions to plan. Planning is a bit of nebulous process to describe even in humans, and while you can see explicit PlanMode use as evidence of one separation, the actual derivation of the tokens to plan are a more complex matter.

**c. Plans and task state**: `[OBSERVED]` · evidence: `Use of the 'EnterPlanMode' tool` \
How does one get created and advanced? What does the model see about task state each turn, and where does it live in the request:
> Claude uses the EnterPlanMode tool in order to create the plan, stores it in a file, and updates that file using the Write tool in order to advance it. It gets to see that Plan Mode has been activated in terms of the task state and it lives like a standard request.

**d. Subagents**: `[INFERRED]` · evidence: `I did not see a subagent get created.` \
When the agent delegates, what the subagent is told, and what comes back:
> I didn't see the agent delegate here, but I would assume that if it did, it would give it a specific task and get some sort of result in return to use later.

**e. Context management**: `[OBSERVED]` · evidence: `Payload is large, contains whole message history + context` \
What changed in the payloads as the session grew:
> The payloads grew as the session grew and remained represented in their original form. Earlier turns are still represented fully, just contained in the json.


## Part V: Reflection

**Two decisions you would copy**, and the problem each solves:
1. Forcing the agent to use the Read tool on a file before using the Edit tool on a file is a strong decision that I would copy. It adds a very important safeguard to make sure that Claude does not hallucinate by editing a file without even knowing what is inside of the file, and seeing that there was a failure where Claude tried to Edit without Read-ing, it's clear that this is an important safeguard to have.
2. The decision to have the tool set be limited and then increase when entering Plan mode is something that I would also copy. Reducing the available tools for a model to use not only makes the context more reasonable, but it also helps keep the model focused rather than using a bunch of extraneous tools that won't help with the task at hand. Keeping the toolset dynamic seems to be a very useful decision.

**One you would make differently** (engage with why it might be there):
> I think that having a tool just to turn on Plan mode is something that I might make differently. It could be useful to add extra attributes to the EnterPlanMode tool like instructions on what the plan needs to be about, which could help speed up the process. However, it does make sense that Anthropic would choose to make the tool very simple to start: just a toggle, because it allows for a very basic trigger that opens up more tools that allow for the complexity to come in later. However, I do think that it could be useful to bake in more information at the start of entering plan mode, to reduce tool redundancy.

**One thing the trace changed** about how you will steer a coding agent:
> The trace made me realize how coding agents work behind the scenes, and I think it makes me want to be a bit more cautious with the verification process for what a model gives back to me and does. I noticed that the path used with the tools is not always linear, and sometimes has weird pitfalls, like the Edit without Read error I saw earlier. While there are safeguards, it makes me question what happens when a safeguard is not adequately in-place, and gave me more of a healthy dose of skepticism, while in the past I treated it more as this magical black box.


## Submission
1. `Command (⌘) + F` for `TODO`. No results means you're done.
2. Confirm no credentials or `x-api-key` headers made it into your quoted excerpts.
3. Push all changes to your remote repository and submit via Gradescope.
4. Don't forget to remove `ANTHROPIC_BASE_URL` from your repo's `.claude/settings.json`!
