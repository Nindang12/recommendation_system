"""Export a sanitized Neo4j graph snapshot for Phase 10 GraphSAGE lifecycle.

This script is read-only against Neo4j. It intentionally excludes secrets,
contact data and embedding vectors from the exported snapshot.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.graphsage.snapshot import GraphSnapshotExporter, snapshot_id_from_time, utc_now_iso  # noqa: E402


def parse_args() -> argparse.Namespace:
    now = utc_now_iso()
    default_output = ROOT / "artifacts" / "graph_snapshots" / f"{snapshot_id_from_time(now)}.json"
    parser = argparse.ArgumentParser(description="Export sanitized Neo4j snapshot for GraphSAGE training")
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--node-limit", type=int, default=10000)
    parser.add_argument("--edge-limit", type=int, default=50000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exporter = GraphSnapshotExporter()
    try:
        payload = exporter.export_to_file(
            args.output,
            node_limit=args.node_limit,
            edge_limit=args.edge_limit,
        )
    finally:
        exporter.graph_repo.close()

    print(json.dumps({"status": "ok", "output": str(args.output), "metadata": payload["metadata"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

