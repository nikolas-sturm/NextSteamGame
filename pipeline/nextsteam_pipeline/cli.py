from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, cast

import typer

from .acquisition import SteamSpyClient
from .audit import audit_build
from .benchmark import benchmark_embeddings, benchmark_indexes, synthetic_vectors, write_report
from .discovery import Eligibility, discover_catalog, select_slice, write_catalog
from .evaluation import candidate_graph_size_report
from .graph import build_candidate_graph
from .ml import QwenEmbeddingAdapter
from .runner import load_canonical, publish_fixture, run_compacted_pipeline, run_pipeline
from .scale import ScaleTarget, acquire_shards, acquire_until_target, compact_shards
from .util import checksum, read_json
from .vector import ZvecIndex

AnyDimension = Literal[512, 768, 1024, 1536, "full"]
IndexKind = Literal["flat", "hnsw"]
VectorDtype = Literal["fp32", "fp16"]

app = typer.Typer(no_args_is_help=True)


def _read_appids(path: Path) -> list[int]:
    return [
        int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@app.command()
def slice(
    appids: Annotated[
        Path, typer.Option(help="Text file containing 100-500 fresh appids, one per line.")
    ],
    workdir: Annotated[Path, typer.Option()] = Path(".pipeline-work"),
    output: Annotated[Path, typer.Option()] = Path("pipeline-output"),
    source_git_sha: Annotated[str, typer.Option()] = "unknown",
    pipeline_git_sha: Annotated[str, typer.Option()] = "unknown",
) -> None:
    """Acquire and publish one thin production slice."""
    values = _read_appids(appids)
    if not 100 <= len(values) <= 500:
        raise typer.BadParameter("thin slice must contain 100-500 appids")
    typer.echo(
        run_pipeline(
            values,
            workdir,
            output,
            source_git_sha=source_git_sha,
            pipeline_git_sha=pipeline_git_sha,
        )
    )


@app.command("discover-catalog")
def discover_catalog_command(
    output: Annotated[Path, typer.Option()],
    pages: Annotated[int, typer.Option(min=1)] = 1,
    min_owners: Annotated[int, typer.Option(min=0)] = 0,
    min_reviews: Annotated[int, typer.Option(min=0)] = 0,
) -> None:
    """Discover fresh deterministic SteamSpy catalog appids and provenance."""
    eligibility = Eligibility(min_owners=min_owners, min_reviews=min_reviews)
    entries, provenance = discover_catalog(SteamSpyClient(), pages, eligibility)
    appids, manifest = write_catalog(output, entries, provenance, eligibility)
    typer.echo(f"{appids}\n{manifest}")


@app.command("select-slice")
def select_slice_command(
    catalog: Annotated[Path, typer.Option(help="catalog.parquet from discover-catalog")],
    output: Annotated[Path, typer.Option()],
    count: Annotated[int, typer.Option(min=100, max=500)] = 500,
    seed: Annotated[str, typer.Option(help="Stable selection seed")] = "nextsteam-v1",
    quantiles: Annotated[int, typer.Option(min=2, max=10)] = 4,
) -> None:
    """Select owner/review-stratified appids; semantic diversity audited later."""
    appids, manifest = select_slice(catalog, output, count, seed, quantiles)
    typer.echo(f"{appids}\n{manifest}")


@app.command("acquire-scale")
def acquire_scale(
    appids: Annotated[Path, typer.Option()],
    workdir: Annotated[Path, typer.Option()],
    target: Annotated[str, typer.Option(help="500, 5000, 20000, or full")] = "500",
    shard_size: Annotated[int, typer.Option(min=1, max=500)] = 500,
) -> None:
    """Acquire bounded resumable shards and deterministically compact them."""
    parsed: object = target if target == "full" else int(target)
    if parsed not in {500, 5000, 20000, "full"}:
        raise typer.BadParameter("target must be 500, 5000, 20000, or full")
    selected = _read_appids(appids)
    target_value = cast(ScaleTarget, parsed)
    if target_value == "full":
        shards = acquire_shards(selected, workdir, shard_size)
        report = compact_shards(shards, workdir / "compacted")
    else:
        shards = acquire_until_target(selected, target_value, workdir, shard_size)
        report = compact_shards(shards, workdir / "compacted", target_value)
    write_report(workdir / "scale-report.json", report)
    typer.echo(workdir / "scale-report.json")


@app.command("build-scale")
def build_scale(
    compacted: Annotated[
        Path, typer.Option(exists=True, file_okay=False, help="Compacted scale directory.")
    ],
    workdir: Annotated[Path, typer.Option()],
    output: Annotated[Path, typer.Option()],
    source_git_sha: Annotated[str, typer.Option()] = "unknown",
    pipeline_git_sha: Annotated[str, typer.Option()] = "unknown",
) -> None:
    """Build an immutable release from integrity-checked compacted shards."""
    typer.echo(
        run_compacted_pipeline(
            compacted,
            workdir,
            output,
            source_git_sha=source_git_sha,
            pipeline_git_sha=pipeline_git_sha,
        )
    )


@app.command("benchmark-embedding")
def benchmark_embedding(
    output: Annotated[Path, typer.Option()],
    revision: Annotated[str, typer.Option()],
    instruction: Annotated[str, typer.Option()],
    dimensions: Annotated[str, typer.Option(help="512, 768, 1024, 1536, or full")] = "1024",
    count: Annotated[int, typer.Option(min=1)] = 100,
    batch_size: Annotated[int, typer.Option(min=1)] = 16,
    bf16: Annotated[bool, typer.Option()] = False,
) -> None:
    """Benchmark cached Qwen embedding model; never downloads model files."""
    parsed: object = dimensions if dimensions == "full" else int(dimensions)
    if parsed not in {512, 768, 1024, 1536, "full"}:
        raise typer.BadParameter("dimensions must be 512, 768, 1024, 1536, or full")
    adapter = QwenEmbeddingAdapter(
        revision, instruction, cast(AnyDimension, parsed), batch_size, bf16
    )
    write_report(
        output,
        benchmark_embeddings(adapter, [f"synthetic benchmark text {i}" for i in range(count)]),
    )


@app.command("benchmark-zvec")
def benchmark_zvec(
    output: Annotated[Path, typer.Option()],
    count: Annotated[int, typer.Option(min=2)] = 1000,
    dimensions: Annotated[int, typer.Option(min=1)] = 512,
    queries: Annotated[int, typer.Option(min=1)] = 20,
    include_fp16: Annotated[bool, typer.Option()] = False,
) -> None:
    """Measure Zvec configurations using deterministic synthetic vectors."""
    vectors = synthetic_vectors(count, dimensions)
    query_vectors = synthetic_vectors(queries, dimensions, seed=11)
    root = output.parent / f".{output.stem}-indexes"

    def factory(kind: str, dtype: str, dims: int) -> ZvecIndex:
        return ZvecIndex(
            root / f"{kind}-{dtype}",
            dims,
            index_kind=cast(IndexKind, kind),
            dtype=cast(VectorDtype, dtype),
        )

    write_report(
        output, benchmark_indexes(factory, vectors, query_vectors, include_fp16=include_fp16)
    )


@app.command("evaluate-candidate-graph")
def evaluate_candidate_graph(
    canonical: Annotated[
        Path,
        typer.Option(
            exists=True,
            dir_okay=False,
            help="canonicalize.data.json from a completed pipeline work directory.",
        ),
    ],
    output: Annotated[Path, typer.Option()],
    k: Annotated[int, typer.Option(min=1)] = 10,
    max_neighbors: Annotated[int, typer.Option(min=1)] = 500,
) -> None:
    """Measure bounded candidate recall against exhaustive ranking."""
    rows = read_json(canonical)
    if not isinstance(rows, list):
        raise typer.BadParameter("canonical input must contain a JSON array")
    report = candidate_graph_size_report(
        load_canonical(rows),
        lambda games: build_candidate_graph(games, max_neighbors=max_neighbors),
        k=k,
    )
    report["source"] = {"path": str(canonical), "sha256": checksum(canonical)}
    write_report(output, report)
    typer.echo(output)


@app.command("audit-build")
def audit_build_command(
    artifact: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option()],
) -> None:
    """Validate one immutable build and report structural and semantic coverage."""
    write_report(output, audit_build(artifact))
    typer.echo(output)


@app.command("publish-test-fixture")
def publish_test_fixture(
    output: Annotated[Path, typer.Option()] = Path("pipeline-test-fixture-output"),
) -> None:
    """Publish newly authored deterministic synthetic artifacts for cross-stack CI only."""
    typer.echo(publish_fixture(output))


if __name__ == "__main__":
    app()
