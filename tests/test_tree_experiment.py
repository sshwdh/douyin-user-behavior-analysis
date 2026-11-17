"""验证树实验拒绝偏离固定配置。"""

import json
from pathlib import Path

import pytest

from douyin_analysis.features import FEATURE_COLUMNS
from douyin_analysis.tree_experiment import verify_protocol
from douyin_analysis.tree_preparation import build_estimators


def test_changed_tree_configuration_rejected(tmp_path: Path) -> None:
    """训练前拒绝修改过的叶节点数量。"""
    (tmp_path / "reports/trees").mkdir(parents=True)
    (tmp_path / "reports/features").mkdir()
    variants = {name: model.get_params() for name, model in build_estimators().items()}
    variants["hgb_15"]["max_leaf_nodes"] = 16
    (tmp_path / "reports/trees/preparation.json").write_text(
        json.dumps({"variants": variants, "features": FEATURE_COLUMNS})
    )
    (tmp_path / "reports/features/manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="偏离"):
        verify_protocol(tmp_path)
