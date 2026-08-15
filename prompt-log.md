## Interaction 1

### User Prompt
# P1 — Set up repository controls

Before any assessment implementation, establish two repository-wide Cursor rules:

1. mandatory interaction logging;
2. pedagogical code documentation.

Do not perform any other assessment work in this interaction.

## Files to create

Create:

```text
prompt-log.md
.cursor/rules/mandatory-prompt-logging.mdc
.cursor/rules/pedagogical-code-documentation.mdc
```

---

## 1. Mandatory interaction logging

Create `prompt-log.md` in the repository root.

For **every Cursor interaction without exception**:

* record my complete prompt exactly as received;
* record your complete user-visible response;
* append chronologically;
* never overwrite, delete, reorder, summarize, truncate, or reconstruct prior entries;
* use sequential interaction numbers beginning with `1`.

Use this format:

```markdown
## Interaction N

### User Prompt
<complete prompt>

### Cursor Response
<complete user-visible response>

---
```

Create `.cursor/rules/mandatory-prompt-logging.mdc` as an **always-applied** Cursor Project Rule enforcing this workflow:

```text
receive prompt
→ perform requested work
→ append complete prompt and complete user-visible response to prompt-log.md
→ verify the entry exists
→ complete the interaction
```

The rule must explicitly state that Cursor Project Rules are behavioral instructions, not a technical guarantee that the platform captures every interaction.

Do not claim stronger enforcement than the platform provides.

---

## 2. Pedagogical code documentation

Create `.cursor/rules/pedagogical-code-documentation.mdc` as an **always-applied** Cursor Project Rule.

Its purpose is to make all new or materially modified code easy for a reviewer to understand.

### General principle

Comments and documentation should explain:

* what the code does;
* why the design exists;
* important architectural boundaries;
* invariants and safeguards;
* non-obvious control flow;
* failure handling;
* relevant tradeoffs.

Prefer explanations of **why** over comments that merely restate syntax.

Example:

Bad:

```python
step += 1  # Increment step.
```

Good:

```python
# The step budget guarantees termination even if the planner repeatedly
# requests actions that do not produce useful evidence.
step += 1
```

### Functions and methods

Every new or materially modified Python function or method must contain a docstring as its first statement.

Use these sections:

* `Description` which includes when to use, when not to use and any edge cases.
* `Input`
* `Output`
* `When to use`
* `When not to use`


Example:

```python
def validate_citation(
    source_id: str,
    evidence: list[EvidenceItem],
) -> bool:
    """Verify that a citation references evidence retrieved in this run.

    Description:
        Checks whether source_id belongs to evidence produced during the
        current agent execution.

    Input:
        source_id:
            Stable source identifier.
        evidence:
            Evidence collected from tool calls during the current run.

    Output:
        True when source_id matches retrieved evidence; otherwise False.

    When to use:
        Before exposing synthesized citations in the final answer.

    When not to use:
        Do not use this function to determine factual correctness. It verifies
        provenance membership only.

    
    """
```

Keep sections concise for simple helpers rather than creating unnecessary documentation volume.

### Modules and classes

New production modules must have a module-level docstring explaining:

* responsibility;
* role in the agent architecture;
* important dependencies or invariants where relevant.

New or materially modified classes must document:

* responsibility;
* lifecycle;
* relationship to other components;
* important state or invariants.

### Inline comments

Add comments where logic is non-obvious, especially around:

* planner/runtime boundaries;
* termination safeguards;
* evidence provenance;
* citation validation;
* state transitions;
* retries and failures;
* duplicate-action handling;
* API quirks;
* timeouts;
* scoring thresholds.

Do not add comments that merely restate obvious code.

### Tests

For non-trivial tests, document:

* the behavior being verified;
* the failure mode being protected against;
* the relevant assessment requirement when useful.

### Scope

This rule applies to:

* production code;
* tests;
* utilities;
* CLI code;
* tool integrations;
* evaluation code.

It applies only to **new or materially modified code**.

Do not modify unrelated existing code solely to add documentation.

Static configuration and JSON/YAML data files are exempt unless documentation is materially useful.

### Completion check

Before completing any coding interaction, verify:

* every new or materially modified function has the required docstring;
* new production modules have module documentation;
* important classes are documented;
* non-obvious logic has useful comments;
* tests explain non-obvious behavioral guarantees;
* documentation still matches the implementation.

---

## 3. Initialize and verify

Before completing this interaction:

1. Create all three required files.
2. Log this exact prompt as `Interaction 1`.
3. Record your complete response under `### Cursor Response`.
4. Verify `prompt-log.md` contains:

   * `## Interaction 1`
   * `### User Prompt`
   * the complete prompt
   * `### Cursor Response`
5. Verify both `.mdc` files:

   * contain valid Cursor rule metadata;
   * are configured with `alwaysApply: true`.
6. Report:

   * files created or modified;
   * verification result for each file.

## Stop condition

After setup and verification, STOP.

### Cursor Response
Repository controls are in place. Three files were created; verification for each is below.

## Files Created

| File | Action |
|------|--------|
| `prompt-log.md` | Created (Interaction 1 initialized) |
| `.cursor/rules/mandatory-prompt-logging.mdc` | Created |
| `.cursor/rules/pedagogical-code-documentation.mdc` | Created |

## Verification Results

### `prompt-log.md`

- `## Interaction 1` — present
- `### User Prompt` — present with the complete prompt
- `### Cursor Response` — present with this complete response
- Chronological append-only format with trailing `---` separator — correct

### `.cursor/rules/mandatory-prompt-logging.mdc`

- Valid YAML frontmatter with `description` — present
- `alwaysApply: true` — confirmed
- Workflow sequence documented (`receive prompt → perform work → append → verify → complete`) — present
- Explicit statement that Project Rules are behavioral instructions, not a platform guarantee — present

### `.cursor/rules/pedagogical-code-documentation.mdc`

- Valid YAML frontmatter with `description` — present
- `alwaysApply: true` — confirmed
- Docstring sections, module/class documentation, inline comment guidance, test documentation, scope, and completion check — all present

No assessment implementation work was performed. Stopping per the stop condition.

---

## Interaction 2

### User Prompt
Create these three files in the repo root/config with the exact content
attached — do not modify, summarize, reformat, or "improve" any of it.
Commit verbatim with message "Project scaffolding: design doc, tool policy,
reference questions" and push to the current branch.

### Cursor Response
Three files were copied byte-for-byte from the attachments into `config/` and committed.

| File | Source |
|------|--------|
| `config/DESIGN.md` | `DESIGN_0904.md` |
| `config/reference_questions.md` | `reference_questions_a538.md` |
| `config/tool_policy.yaml` | `tool_policy_1ca3.yaml` |

`diff -q` confirmed each destination file matches its source exactly — no content changes.

**Commit:** `5426e07` — `Project scaffolding: design doc, tool policy, reference questions`

**Branch:** `cursor/p1-repository-controls-72ca` (pushed to origin)

---
