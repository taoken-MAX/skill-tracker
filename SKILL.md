---
name: skill-tracker
description: Track skill usage, identify unused skills with zero calls, and clean up stale skills after a 7-day danger period. Use when the user wants to check which installed skills are never used, audit skill call frequency, or set up automatic skill cleanup.
---

# Skill Tracker

Track usage of installed skills, detect ghost skills (no SKILL.md on disk), and clean up stale skills.

## How it works

Every time any skill is invoked, a PostToolUse hook records the call to `~/.claude/skills-tracker/tracking.json`. This skill reads that data and runs two passes:

**Pass 1 — Ghost detection:** Find skills referenced in `skills-lock.json` or `tracking.json` that have no SKILL.md on disk. These are "ghost skills" — they appear to exist but cannot be invoked. Ask the user if they want to clean them up immediately.

**Pass 2 — Lifecycle:** Apply lifecycle rules to real skills:
- **7 days** with zero calls → marked as "danger"
- **Another 7 days** still zero calls → ready for deletion
- Called at any time → danger mark cleared, timer resets

Each skill's description is auto-discovered from its SKILL.md frontmatter (local file or GitHub source) and cached in tracking.json.

System built-in skills and the tracker itself are excluded from tracking.

## Usage

### Manual mode (default)

When invoked without `--auto`, run the check script:

```bash
python ~/.claude/skills/skill-tracker/scripts/check-skills.py
```

Then present the results:

1. **Ghost skills** (no SKILL.md on disk): flag immediately, ask user if they want to clean up
2. **Scope** (local/global/both/reference): show where each skill lives
3. **Top 3** most called: show your most-used skills
4. **Healthy** (calls > 0): show call count and last-call date
5. **Idle** (0 calls, not danger): show days until danger mark
6. **Danger** (marked, counting down): show days until deletion
7. **Stale** (ready to delete): ask which to delete

For delete-ready skills, ask the user which ones to delete. For each confirmed deletion:
- Remove the skill's directory from `.claude/skills/` or wherever it lives
- Remove the entry from `skills-lock.json` if present
- Remove the entry from `tracking.json`

### Auto mode (`--auto`)

```bash
python ~/.claude/skills/skill-tracker/scripts/check-skills.py --auto
```

Same as manual, but the script automatically marks danger on qualifying skills.

## Skill discovery

The tracker automatically discovers skills from:
- `skills-lock.json` in the current project (extracts GitHub source info for description lookup)
- `.claude/skills/` directories (project and global)

## Description resolution

For each skill, descriptions are resolved in this order:
1. **Tracking cache** — if already stored in tracking.json, reuse immediately
2. **Local SKILL.md** — read the YAML frontmatter `description` field from the skill's SKILL.md on disk
3. **GitHub fetch** — for skills from `skills-lock.json` with a GitHub source, curl the raw SKILL.md and extract the description

Descriptions are cached permanently in tracking.json after the first successful fetch.

## Notes

- Hook writes are handled by `~/.claude/skills/skill-tracker/scripts/record-call.py` via PostToolUse hook
- Tracking data lives at `~/.claude/skills-tracker/tracking.json`
- This skill runs on every invocation, so its own call count will never hit zero
