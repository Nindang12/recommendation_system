from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import (
    DEFAULT_BASELINE_NAME,
    DEFAULT_CANDIDATE_NAME,
    DEFAULT_DIMENSION,
    DEFAULT_MIN_POSITIVE_EDGES,
    DEFAULT_RANDOM_SEED,
    MODEL_STATUS_CANDIDATE,
    MODEL_STATUS_REJECTED,
)
from .dataset import GraphDatasetBuilder
from .encoder import NodeFeatureEncoder
from .registry import ModelRegistry, utc_now_iso
from .snapshot import load_snapshot


class GraphSAGECandidateTrainer:
    """Offline candidate trainer.

    If PyTorch Geometric is unavailable or the dataset is too small, this class
    still emits registry artifacts and a truthful evaluation report. It never
    promotes or mutates runtime state.
    """

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_CANDIDATE_NAME,
        dimension: int = DEFAULT_DIMENSION,
        min_positive_edges: int = DEFAULT_MIN_POSITIVE_EDGES,
        random_seed: int = DEFAULT_RANDOM_SEED,
        evaluation_baseline: str = DEFAULT_BASELINE_NAME,
        registry: Optional[ModelRegistry] = None,
    ) -> None:
        self.model_name = model_name
        self.dimension = int(dimension)
        self.min_positive_edges = int(min_positive_edges)
        self.random_seed = int(random_seed)
        self.evaluation_baseline = evaluation_baseline
        self.registry = registry or ModelRegistry()

    def train_from_snapshot(self, snapshot_path: Path) -> Dict[str, Any]:
        snapshot = load_snapshot(snapshot_path)
        training_data_version = str(snapshot.get("snapshot_id") or snapshot_path.stem)
        encoder = NodeFeatureEncoder(dimension=self.dimension)
        node_features = encoder.encode_snapshot(snapshot)
        dataset = GraphDatasetBuilder(random_seed=self.random_seed).build(snapshot, node_features)
        model_dir = self.registry.candidate_dir(self.model_name)
        self.registry.ensure_active_pointer()

        encoder.save(model_dir / "node_feature_encoder.pkl")
        (model_dir / "graphsage_config.json").write_text(
            json.dumps(
                {
                    "model": "GraphSAGE",
                    "layers": 2,
                    "hidden_dim": self.dimension,
                    "output_dim": self.dimension,
                    "neighbor_sampling": [10, 5],
                    "random_seed": self.random_seed,
                    "training_data_version": training_data_version,
                    "evaluation_baseline": self.evaluation_baseline,
                    "active_runtime_unchanged": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        pyg_available = self._torch_geometric_available()
        warnings = []
        status = "candidate_artifact_created"
        promote_allowed = False
        model_status = MODEL_STATUS_CANDIDATE
        training_mode = "graphsage_real_candidate"

        if dataset.stats["positive_edges"] < self.min_positive_edges:
            warnings.append(
                f"positive_edges_below_threshold({dataset.stats['positive_edges']}<{self.min_positive_edges})"
            )
            status = "insufficient_data_warning"
            model_status = MODEL_STATUS_REJECTED
            training_mode = "lifecycle_scaffold_only"
        elif not pyg_available:
            warnings.append("torch_geometric_unavailable; emitted fallback candidate artifact only")
            status = "pyg_unavailable_warning"
            training_mode = "fallback_stub"
        else:
            warnings.append("real_training_not_enabled_in_safe_phase10_scaffold")
            status = "safe_scaffold_no_runtime_promotion"

        model_stub_path = model_dir / "model_stub.json"
        model_stub_path.write_text(
            json.dumps(
                {
                    "status": status,
                    "training_mode": training_mode,
                    "dimension": self.dimension,
                    "normalized": True,
                    "note": "Runtime worker still uses GraphSAGE-lite until explicit promotion.",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        report = {
            "status": status,
            "created_at": utc_now_iso(),
            "model_name": self.model_name,
            "model_status": model_status,
            "promote_allowed": promote_allowed,
            "training_data_version": training_data_version,
            "evaluation_baseline": self.evaluation_baseline,
            "snapshot_path": str(snapshot_path),
            "dataset_stats": dataset.stats,
            "minimum_data_thresholds": {
                "min_positive_edges": self.min_positive_edges,
                "min_nodes": 2,
            },
            "pyg_available": pyg_available,
            "warnings": warnings,
            "runtime_unchanged": True,
        }
        evaluation_report_path = self.registry.write_evaluation_report(self.model_name, report)
        metadata_path = self.registry.write_metadata(
            self.model_name,
            {
                "model_status": model_status,
                "training_data_version": training_data_version,
                "evaluation_baseline": self.evaluation_baseline,
                "dimension": self.dimension,
                "artifact_dir": str(model_dir),
                "model_artifact": str(model_stub_path),
                "encoder_artifact": str(model_dir / "node_feature_encoder.pkl"),
                "evaluation_report": str(evaluation_report_path),
                "promote_allowed": promote_allowed,
                "runtime_unchanged": True,
                "warnings": warnings,
            },
        )
        report["metadata_path"] = str(metadata_path)
        return report

    @staticmethod
    def _torch_geometric_available() -> bool:
        try:
            import torch_geometric  # noqa: F401

            return True
        except Exception:
            return False

