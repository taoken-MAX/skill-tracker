"""Check skill usage, detect ghost skills, and apply 7/14 day lifecycle logic."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

TRACKING_FILE = os.path.expanduser("~/.claude/skills-tracker/tracking.json")

SYSTEM_SKILLS = {
    "update-config", "keybindings-help", "verify", "code-review",
    "simplify", "fewer-permission-prompts", "loop", "claude-api",
    "run", "init", "review", "security-review",
}

TRACKER_SKILL = "skill-tracker"

DANGER_DAYS = 7
DELETE_DAYS = 7


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tracking(data):
    os.makedirs(os.path.dirname(TRACKING_FILE), exist_ok=True)
    with open(TRACKING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_frontmatter_description(text):
    """Extract description from YAML frontmatter of a SKILL.md file."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    fm = m.group(1)
    lines = fm.split("\n")

    for i, line in enumerate(lines):
        if line.startswith("description:"):
            value = line.split(":", 1)[1].strip()
            if value in (">", "|"):
                parts = []
                for next_line in lines[i + 1:]:
                    stripped = next_line.strip()
                    if not stripped:
                        break
                    parts.append(stripped)
                return " ".join(parts) if parts else None
            return value.strip().strip('"').strip("'")

    for line in text.split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return None


def skill_has_local_file(name):
    """Check if a skill has a real SKILL.md on disk."""
    dirs = []
    project = os.path.join(os.getcwd(), ".claude", "skills")
    if os.path.isdir(project):
        dirs.append(project)
    global_ = os.path.expanduser("~/.claude/skills")
    if os.path.isdir(global_):
        dirs.append(global_)

    for base in dirs:
        skill_md = os.path.join(base, name, "SKILL.md")
        if os.path.exists(skill_md):
            return True
    return False


def detect_ghost_skills():
    """Find skills that are referenced but have no SKILL.md on disk.

    Returns list of dicts with name, source (where referenced), and suggested action.
    """
    ghosts = []

    # Check skills-lock.json
    lock_path = "skills-lock.json"
    if os.path.exists(lock_path):
        lock_data = load_json(lock_path)
        for name in lock_data.get("skills", {}):
            if name in SYSTEM_SKILLS or name == TRACKER_SKILL:
                continue
            if not skill_has_local_file(name):
                ghosts.append({
                    "name": name,
                    "source": "skills-lock.json",
                    "has_description": bool(lock_data["skills"][name].get("skillPath")),
                })

    # Check tracking.json
    tracking = load_json(TRACKING_FILE)
    for name in tracking.get("skills", {}):
        if name in SYSTEM_SKILLS or name == TRACKER_SKILL:
            continue
        if not skill_has_local_file(name):
            # Avoid duplicates
            if not any(g["name"] == name for g in ghosts):
                ghosts.append({
                    "name": name,
                    "source": "tracking.json",
                    "has_description": bool(tracking["skills"][name].get("description")),
                })

    return ghosts


def clean_ghost_skills(ghost_names):
    """Remove ghost skills from skills-lock.json and tracking.json."""
    cleaned = {"skills-lock.json": False, "tracking.json": False}

    # Clean skills-lock.json
    lock_path = "skills-lock.json"
    if os.path.exists(lock_path):
        lock_data = load_json(lock_path)
        skills = lock_data.get("skills", {})
        removed = False
        for name in list(skills.keys()):
            if name in ghost_names:
                del skills[name]
                removed = True
        if removed:
            with open(lock_path, "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2, ensure_ascii=False)
            cleaned["skills-lock.json"] = True

    # Clean tracking.json
    tracking = load_json(TRACKING_FILE)
    if os.path.exists(TRACKING_FILE):
        tskills = tracking.get("skills", {})
        removed = False
        for name in list(tskills.keys()):
            if name in ghost_names:
                del tskills[name]
                removed = True
        if removed:
            with open(TRACKING_FILE, "w", encoding="utf-8") as f:
                json.dump(tracking, f, indent=2, ensure_ascii=False)
            cleaned["tracking.json"] = True

    return cleaned


def fetch_github_description(source, skill_path):
    """Try to fetch a skill description from GitHub raw content."""
    url = f"https://raw.githubusercontent.com/{source}/main/{skill_path}"
    try:
        result = subprocess.run(
            ["curl", "-sL", "--connect-timeout", "5", "--max-time", "10", url],
            capture_output=True, timeout=12
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.decode("utf-8", errors="replace")
            return extract_frontmatter_description(text)
    except Exception:
        pass
    return None


def discover_skills():
    """Discover all installed non-system skills and their metadata."""
    found = {}

    # 1. From skills-lock.json
    lock_path = "skills-lock.json"
    if os.path.exists(lock_path):
        lock_data = load_json(lock_path)
        for name, info in lock_data.get("skills", {}).items():
            if name not in SYSTEM_SKILLS and name != TRACKER_SKILL:
                found[name] = {
                    "source": info.get("source"),
                    "skill_path": info.get("skillPath"),
                    "in_project": False,
                    "in_global": False,
                }

    # 2. From project .claude/skills/
    project_skills = os.path.join(os.getcwd(), ".claude", "skills")
    if os.path.isdir(project_skills):
        for entry in os.listdir(project_skills):
            if entry in SYSTEM_SKILLS or entry == TRACKER_SKILL:
                continue
            entry_path = os.path.join(project_skills, entry)
            if os.path.isdir(entry_path):
                skill_md = os.path.join(entry_path, "SKILL.md")
                if os.path.exists(skill_md):
                    if entry not in found:
                        found[entry] = {}
                    found[entry]["local_path"] = entry_path
                    found[entry]["in_project"] = True

    # 3. From global ~/.claude/skills/
    global_skills = os.path.expanduser("~/.claude/skills")
    if os.path.isdir(global_skills):
        for entry in os.listdir(global_skills):
            if entry in SYSTEM_SKILLS or entry == TRACKER_SKILL:
                continue
            entry_path = os.path.join(global_skills, entry)
            if os.path.isdir(entry_path):
                skill_md = os.path.join(entry_path, "SKILL.md")
                if os.path.exists(skill_md):
                    if entry not in found:
                        found[entry] = {}
                    found[entry]["local_path"] = entry_path
                    found[entry]["in_global"] = True

    # Resolve scope for each skill
    for name, meta in found.items():
        in_proj = meta.get("in_project", False)
        in_glob = meta.get("in_global", False)
        if in_proj and in_glob:
            meta["scope"] = "both"
        elif in_proj:
            meta["scope"] = "local"
        elif in_glob:
            meta["scope"] = "global"
        else:
            meta["scope"] = "reference"  # skills-lock.json only

    return found


def get_skill_description(name, meta):
    """Get description for a skill. Returns None if not available."""
    if "local_path" in meta:
        skill_md = os.path.join(meta["local_path"], "SKILL.md")
        if os.path.exists(skill_md):
            try:
                with open(skill_md, "r", encoding="utf-8") as f:
                    return extract_frontmatter_description(f.read())
            except Exception:
                pass

    if meta.get("source") and meta.get("skill_path"):
        return fetch_github_description(meta["source"], meta["skill_path"])

    return None


def discover_skill_dirs():
    """Return list of base directories that contain skill folders."""
    dirs = []
    project_skills = os.path.join(os.getcwd(), ".claude", "skills")
    if os.path.isdir(project_skills):
        dirs.append(project_skills)
    global_skills = os.path.expanduser("~/.claude/skills")
    if os.path.isdir(global_skills):
        dirs.append(global_skills)
    return dirs


def run(auto_mode=False):
    data = load_json(TRACKING_FILE)
    if "skills" not in data:
        data["skills"] = {}

    # ---- Step 0: Ghost skill detection ----
    ghosts = detect_ghost_skills()

    discovered = discover_skills()
    skill_dirs = discover_skill_dirs()
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()
    changed = False

    # Register newly discovered skills (only real ones, not ghosts)
    for name, meta in discovered.items():
        if name not in data["skills"]:
            data["skills"][name] = {
                "first_seen": now_str,
                "last_called": None,
                "call_count": 0,
                "marked_danger": None,
            }
            changed = True

    # Resolve descriptions for all tracked skills
    for name, meta in discovered.items():
        entry = data["skills"].get(name)
        if not entry:
            continue
        if entry.get("description"):
            continue
        desc = get_skill_description(name, meta)
        if desc:
            entry["description"] = desc
            changed = True

    if changed:
        save_tracking(data)

    # ---- Apply lifecycle logic ----
    healthy = []
    warning_idle = []
    warning_danger = []
    delete_candidates = []

    for name, entry in list(data["skills"].items()):
        meta = discovered.get(name)
        if not meta:
            continue

        call_count = entry.get("call_count", 0)
        marked_danger = entry.get("marked_danger")
        first_seen_str = entry.get("first_seen")
        last_called_str = entry.get("last_called")
        description = entry.get("description", "")
        scope = meta.get("scope", "unknown")

        if call_count > 0:
            if marked_danger:
                entry["marked_danger"] = None
                changed = True
            healthy.append({
                "name": name,
                "call_count": call_count,
                "last_called": last_called_str,
                "description": description,
                "scope": scope,
            })
            continue

        first_seen = datetime.fromisoformat(first_seen_str) if first_seen_str else None

        if marked_danger:
            mark_date = datetime.fromisoformat(marked_danger)
            days_since_mark = (now - mark_date).days
            days_until_delete = DELETE_DAYS - days_since_mark
            if days_since_mark >= DELETE_DAYS:
                delete_candidates.append({
                    "name": name,
                    "first_seen": first_seen_str,
                    "marked_danger": marked_danger,
                    "days_since_mark": days_since_mark,
                    "description": description,
                    "scope": scope,
                })
            else:
                warning_danger.append({
                    "name": name,
                    "first_seen": first_seen_str,
                    "marked_danger": marked_danger,
                    "days_until_delete": days_until_delete,
                    "description": description,
                    "scope": scope,
                })
        else:
            if first_seen:
                days_since_first = (now - first_seen).days
                if days_since_first >= DANGER_DAYS:
                    if auto_mode:
                        entry["marked_danger"] = now_str
                        changed = True
                    warning_danger.append({
                        "name": name,
                        "first_seen": first_seen_str,
                        "days_since_first": days_since_first,
                        "description": description,
                        "scope": scope,
                    })
                else:
                    warning_idle.append({
                        "name": name,
                        "first_seen": first_seen_str,
                        "days_since_first": days_since_first,
                        "days_until_danger": DANGER_DAYS - days_since_first,
                        "description": description,
                        "scope": scope,
                    })

    if changed:
        save_tracking(data)

    # ---- Top 3 most called ----
    all_with_calls = []
    for name, entry in data["skills"].items():
        cc = entry.get("call_count", 0)
        if cc > 0:
            meta = discovered.get(name, {})
            all_with_calls.append({
                "name": name,
                "call_count": cc,
                "description": entry.get("description", ""),
                "scope": meta.get("scope", "unknown"),
            })
    all_with_calls.sort(key=lambda x: x["call_count"], reverse=True)
    top3 = all_with_calls[:3]

    # ---- Scope breakdown ----
    local_skills = [n for n, m in discovered.items() if m.get("scope") == "local"]
    global_skills = [n for n, m in discovered.items() if m.get("scope") == "global"]
    both_skills = [n for n, m in discovered.items() if m.get("scope") == "both"]
    ref_skills = [n for n, m in discovered.items() if m.get("scope") == "reference"]

    # ---- Summary output ----
    print()
    if ghosts:
        ghost_names = ", ".join(g["name"] for g in ghosts)
        print(f"!! GHOST SKILLS ({len(ghosts)}): {ghost_names}")
        print(f"   No SKILL.md on disk — CANNOT be invoked.")
    else:
        print("OK: No ghost skills detected.")

    print()
    if local_skills:
        print(f"LOCAL (project only): {', '.join(local_skills)}")
    if global_skills:
        print(f"GLOBAL (all projects): {', '.join(global_skills)}")
    if both_skills:
        print(f"BOTH (local + global): {', '.join(both_skills)}")
    if ref_skills:
        print(f"REF (skills-lock.json only): {', '.join(ref_skills)}")

    print()
    if top3:
        print(f"TOP 3 MOST CALLED:")
        for i, s in enumerate(top3, 1):
            print(f"  {i}. {s['name']} — {s['call_count']} calls [{s['scope']}] — {s['description']}")
    else:
        print("TOP 3: No calls recorded yet.")

    print()
    print(f"SKILL TRACKER | {now.strftime('%Y-%m-%d')} | {len(healthy)} active | {len(warning_idle)} idle | {len(warning_danger)} danger | {len(delete_candidates)} stale")
    if healthy:
        names = ", ".join(s["name"] for s in healthy)
        print(f"  ACTIVE: {names}")
    if warning_idle:
        names = ", ".join(s["name"] for s in warning_idle)
        print(f"  IDLE (0 calls): {names}")
    if warning_danger:
        names = ", ".join(s["name"] for s in warning_danger)
        print(f"  DANGER: {names}")
    if delete_candidates:
        names = ", ".join(s["name"] for s in delete_candidates)
        print(f"  STALE: {names}")
    if not healthy and not warning_idle and not warning_danger and not delete_candidates:
        print("  No real skills tracked yet.")
    print()

    # ---- JSON output ----
    report = {
        "mode": "auto" if auto_mode else "manual",
        "ghost_skills": ghosts,
        "total_tracked": len(data["skills"]),
        "total_installed": len(discovered),
        "scope_breakdown": {
            "local": len(local_skills),
            "global": len(global_skills),
            "both": len(both_skills),
            "reference": len(ref_skills),
        },
        "top3": top3,
        "healthy": healthy,
        "warning_idle": warning_idle,
        "warning_danger": warning_danger,
        "delete_candidates": delete_candidates,
        "danger_days": DANGER_DAYS,
        "delete_days": DELETE_DAYS,
    }

    print("---JSON---")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    # Return ghost info for auto-cleanup prompt
    return report


if __name__ == "__main__":
    auto = "--auto" in sys.argv
    run(auto_mode=auto)
