# Skill Tracker

Track Claude Code skill usage, detect ghost skills, and clean up stale skills automatically.

## Features

- **Ghost detection** — find skills with no SKILL.md on disk that appear in tracking/lock files but can never be invoked
- **Scope breakdown** — see which skills are project-local vs global
- **Top 3 ranking** — know which skills you use most
- **Lifecycle management** — 7 days unused → danger → 7 more days → ready to delete
- **Auto-description** — fetches skill descriptions from SKILL.md frontmatter (local or GitHub)

## Install

```bash
# Clone to global skills directory
git clone https://github.com/YOUR_USERNAME/skill-tracker.git ~/.claude/skills/skill-tracker
```

Add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Skill",
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.claude/skills/skill-tracker/scripts/record-call.py",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

## Usage

```
/skill-tracker
```

Three passes per run:

1. **Ghost detection** — flag skills with no SKILL.md on disk
2. **Scope breakdown** — local vs global vs reference  
3. **Usage report** — healthy / idle / danger / stale, plus top 3 most-called

### Auto mode

```
/skill-tracker --auto
```

Auto-marks danger on skills idle past 7 days.

## Lifecycle

```
First seen ──7 days──▶ Danger ──7 days──▶ Delete candidate
    │                      │
    └── any call ──▶ Reset  └── any call ──▶ Reset
```
