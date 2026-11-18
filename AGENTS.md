## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues on acc-aqt/framewise, using the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The default label names are used: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one root `GLOSSARY.md` plus `docs/adr/`. See `docs/agents/domain.md`.

## Changelog

Every pull request with a change a photographer can notice adds a line to `## Unreleased` in `CHANGELOG.md`, in the same pull request. See ADR-0007.

- Write for photographers: say what changed for them, in Glossary terms, not what changed in the code.
- Refactors, tests, CI, docs for contributors and other internal changes get no entry.
- Keep to the shape the Review UI renders: bullets, optionally under `### ` subheadings, with only `**bold**` and `` `code` `` as inline formatting. No links, images or nested lists.
