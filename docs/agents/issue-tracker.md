# Issue tracker: GitHub

Issues and specs live as GitHub issues on acc-aqt/framewise. Use the `gh` CLI; it infers the repo when run inside a clone. Labels are in [triage-labels.md](triage-labels.md).

When a skill says "publish to the issue tracker", create an issue. When it says "fetch the relevant ticket", read it.

## Commands

- **Create**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read**: `gh issue view <n> --json number,title,body,labels,comments`
- **List**: `gh issue list --state open --label <label> --json number,title,labels`
- **Comment**: `gh issue comment <n> --body "..."`
- **Label**: `gh issue edit <n> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <n> --comment "..."`

## Sub-issues and blocking

Tickets that belong to a larger piece of work are linked with GitHub's native sub-issues and issue dependencies.

- **Sub-issue**: `gh issue create --parent <parent> ...`, or `gh issue edit <parent> --add-sub-issue <child>` for an existing issue.
- **Blocked by**: `gh api --method POST repos/acc-aqt/framewise/issues/<n>/dependencies/blocked_by -F issue_id=<blocker-id>`. `<blocker-id>` is the blocker's database id (`gh api repos/acc-aqt/framewise/issues/<blocker> --jq .id`), not its `#number` or `node_id`.
- A ticket is unblocked when `issue_dependencies_summary.blocked_by` (open blockers only) is 0, which you can read with `gh api repos/acc-aqt/framewise/issues/<n>`.

## Pull requests

**PRs as a request surface: no.** `/triage` reads this flag; external PRs are not treated as feature requests.
