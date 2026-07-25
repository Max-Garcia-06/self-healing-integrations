# CLAUDE.md

Two-person hackathon repo. Biggest risk: editing each other's files. Follow this exactly.

## Ownership

**Max owns:** `prompts/`, `context/`, `src/`, `tests/`, `examples/`, `user_stories/`, `architecture.json`, `.pddrc`, `.pdd/`, `integrations/shipfast/adapter.prompt`

**Lawrence owns:** `mock_upstream/`, `workflows/`, `sponsors/`, `fixtures/`

**Rule:** Never create, edit, move, or delete a file in Lawrence's directories. If a change appears needed there, stop and say so — do not make it.

## PDD

- Never run any `pdd` subcommand.
- Never edit anything under `.pdd/`.
- Never edit generated files in `src/` or `tests/` directly — they are regenerated from prompts.
- If generated code looks wrong, the fix belongs in the `.prompt` file, not the generated output.

## Context Snapshots

`context/specs/shipfast/*.json` are pinned vendor specs.

- Never edit them to make code work.
- They are replaced wholesale, never patched.

## Git

- Work on `main`.
- Never commit files outside Max's directories.
- Keep commits small.
