from pathlib import Path

import pytest

from nextsteam_pipeline.vector import ZvecIndex


def test_zvec_persists_and_queries(tmp_path: Path) -> None:
    path = tmp_path / "vectors"
    index = ZvecIndex(path, dimensions=3, index_kind="flat")
    index.upsert(
        ["game_1", "game_2"],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [{"lane": "mechanics"}, {"lane": "vibe"}],
    )

    assert index.query([1.0, 0.0, 0.0], 1)[0][0] == "game_1"
    index.close()
    reopened = ZvecIndex(path, dimensions=3)
    assert reopened.query([0.0, 1.0, 0.0], 1)[0][0] == "game_2"


def test_zvec_chunks_writes_above_native_batch_limit(tmp_path: Path) -> None:
    index = ZvecIndex(tmp_path / "vectors", dimensions=2)
    count = 1025

    index.upsert(
        [f"game_{item}" for item in range(count)],
        [[1.0, float(item % 2)] for item in range(count)],
        [{"item": item} for item in range(count)],
    )

    assert index.query([1.0, 0.0], 1)
    index.close()


def test_zvec_rejects_invalid_shapes(tmp_path: Path) -> None:
    index = ZvecIndex(tmp_path / "vectors", dimensions=2)
    with pytest.raises(ValueError, match="equal lengths"):
        index.upsert(["game:1"], [], [])
    with pytest.raises(ValueError, match="2 dimensions"):
        index.query([1.0], 1)
