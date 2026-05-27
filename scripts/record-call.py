"""Record skill calls from PostToolUse hook stdin JSON."""
import json
import sys
import os
from datetime import datetime, timezone

TRACKING_FILE = os.path.expanduser("~/.claude/skills-tracker/tracking.json")

# System skills that should never be tracked/deleted
SYSTEM_SKILLS = {
    "update-config", "keybindings-help", "verify", "code-review",
    "simplify", "fewer-permission-prompts", "loop", "claude-api",
    "run", "init", "review", "security-review",
}

# The tracker itself should not be tracked
TRACKER_SKILL = "skill-tracker"


def load_tracking():
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "skills" not in data:
            data["skills"] = {}
        return data
    return {"skills": {}}


def save_tracking(data):
    os.makedirs(os.path.dirname(TRACKING_FILE), exist_ok=True)
    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        hook_data = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool_name = hook_data.get("tool_name", "")
    if tool_name != "Skill":
        return

    tool_input = hook_data.get("tool_input", {})
    command = tool_input.get("command", tool_input.get("skill", ""))
    if not command:
        return

    # Extract skill name (first word before space, handles "gstack --args")
    skill_name = command.strip().split()[0]

    if skill_name in SYSTEM_SKILLS or skill_name == TRACKER_SKILL:
        return

    data = load_tracking()
    now = datetime.now(timezone.utc).isoformat()
    skills = data["skills"]

    if skill_name not in skills:
        skills[skill_name] = {
            "first_seen": now,
            "last_called": now,
            "call_count": 1,
            "marked_danger": None,
        }
    else:
        entry = skills[skill_name]
        entry["last_called"] = now
        entry["call_count"] = entry.get("call_count", 0) + 1
        # Clear danger mark if it was called again
        if entry.get("marked_danger"):
            entry["marked_danger"] = None

    save_tracking(data)


if __name__ == "__main__":
    main()
