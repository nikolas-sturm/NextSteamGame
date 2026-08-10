from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, cast

import typer

from .acquisition import SteamSpyClient
from .benchmark import benchmark_embeddings, benchmark_indexes, synthetic_vectors, write_report
from .discovery import Eligibility, discover_catalog, select_slice, write_catalog
from .ml import QwenEmbeddingAdapter
from .runner import publish_fixture, run_pipeline
from .scale import ScaleTarget, acquire_shards, bounded_appids, compact_shards
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
    selected = bounded_appids(_read_appids(appids), cast(ScaleTarget, parsed))
    shards = acquire_shards(selected, workdir, shard_size)
    write_report(workdir / "scale-report.json", compact_shards(shards, workdir / "compacted"))
    typer.echo(workdir / "scale-report.json")


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


@app.command("publish-test-fixture")
def publish_test_fixture(
    output: Annotated[Path, typer.Option()] = Path("pipeline-test-fixture-output"),
) -> None:
    """Publish newly authored deterministic synthetic artifacts for cross-stack CI only."""
    typer.echo(publish_fixture(output))


if __name__ == "__main__":
    app()
