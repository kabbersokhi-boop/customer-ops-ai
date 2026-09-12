import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "n8n"
FORBIDDEN_KEYS = {"credentials"}


def main() -> int:
    paths = sorted(WORKFLOW_DIR.glob("*.json"))
    if len(paths) != 8:
        raise SystemExit(f"Expected 8 workflow exports, found {len(paths)}")
    ids: set[str] = set()
    names: set[str] = set()
    for path in paths:
        workflow = json.loads(path.read_text(encoding="utf-8"))
        serialized = json.dumps(workflow)
        if "$env." in serialized:
            raise SystemExit(f"{path.name}: use n8n Variables ($vars), not blocked expression environment access")
        workflow_id = workflow.get("id")
        name = workflow.get("name")
        nodes = workflow.get("nodes")
        if not workflow_id or not name or not isinstance(nodes, list) or not nodes:
            raise SystemExit(f"{path.name}: missing id, name, or nodes")
        if workflow_id in ids or name in names:
            raise SystemExit(f"{path.name}: duplicate workflow id or name")
        ids.add(workflow_id)
        names.add(name)
        for node in nodes:
            if not {"id", "name", "type", "typeVersion", "position"} <= node.keys():
                raise SystemExit(f"{path.name}: incomplete node {node.get('name', '<unknown>')}")
            if FORBIDDEN_KEYS & node.keys():
                raise SystemExit(f"{path.name}: exported credentials are forbidden")
    print(f"Validated {len(paths)} credential-free n8n workflow exports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
