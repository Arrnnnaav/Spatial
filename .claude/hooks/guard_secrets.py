"""PreToolUse guard: keys live in server/.env — never read or edit it through a tool; never edit SQLite files.
Exit 2 blocks the tool call and shows the reason to Claude."""

import json
import sys

data = json.load(sys.stdin)
tool = data.get("tool_name", "")
path = (
    str((data.get("tool_input") or {}).get("file_path") or "")
    .replace("\\", "/")
    .lower()
)

if path.endswith("server/.env"):
    print(
        "Blocked: server/.env holds API keys. Use server/.env.example, or check key presence without printing values.",
        file=sys.stderr,
    )
    sys.exit(2)
if tool in {"Edit", "Write"} and path.endswith(".db"):
    print("Blocked: SQLite databases are not edited by hand.", file=sys.stderr)
    sys.exit(2)
