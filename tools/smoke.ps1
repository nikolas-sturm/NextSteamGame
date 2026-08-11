param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactDir,
    [int]$Port = 18080,
    [string]$LoadOutput = "",
    [int]$LoadRequests = 1000,
    [int]$LoadConcurrency = 25,
    [int]$ReadyTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifact = (Resolve-Path -LiteralPath $ArtifactDir).Path
$manifest = Get-Content -LiteralPath (Join-Path $artifact "manifest.json") -Raw | ConvertFrom-Json
$metadata = Get-Content -LiteralPath (Join-Path $artifact "metadata.json") -Raw | ConvertFrom-Json
$graph = Get-Content -LiteralPath (Join-Path $artifact "graph.json") -Raw | ConvertFrom-Json
$searchTarget = $metadata.games | Select-Object -First 1
$seedRecord = $graph.records | Where-Object { $_.candidates.Count -gt 0 } | Select-Object -First 1
if ($null -eq $searchTarget -or $null -eq $seedRecord) {
    throw "Artifact needs at least one game and one candidate edge"
}
$expectedMode = if (
    (Test-Path -LiteralPath (Join-Path $artifact "vectors/config.json")) -and
    $seedRecord.candidates.Count -lt 50
) { "dynamic_vector" } else { "candidate_graph" }
$expectedTop = $seedRecord.candidates | Sort-Object -Property @(
    @{ Expression = {
        [double]$_.lane_similarities.mechanics + [double]$_.lane_similarities.narrative +
        [double]$_.lane_similarities.vibe + [double]$_.lane_similarities.structure_loop
    }; Descending = $true },
    @{ Expression = { [int]$_.appid }; Ascending = $true }
) | Select-Object -First 1

& cargo build --locked -p api --manifest-path "$repoRoot/Cargo.toml"
if ($LASTEXITCODE -ne 0) {
    throw "API build failed"
}
$zvecLibrary = [IO.Directory]::EnumerateFiles(
    (Join-Path $repoRoot "target/debug/build"),
    "zvec_c_api.dll",
    [IO.SearchOption]::AllDirectories
) | Select-Object -First 1
if ($null -eq $zvecLibrary) {
    throw "Zvec runtime library was not produced"
}

$environment = @{
    ARTIFACT_DIR = $artifact
    API_BIND = "127.0.0.1:$Port"
    PATH = "$(Split-Path -Parent $zvecLibrary);$env:PATH"
    RUST_LOG = "warn"
}
if ($manifest.acquisition_windows.kind -eq "test_fixture") {
    $environment.ALLOW_FIXTURE_ARTIFACTS = "1"
}
$binary = Join-Path $repoRoot "target/debug/api.exe"
$process = Start-Process -FilePath $binary -PassThru -NoNewWindow -Environment $environment

try {
    $ready = $false
    foreach ($attempt in 1..($ReadyTimeoutSeconds * 4)) {
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/readyz" | Out-Null
            $ready = $true
            break
        } catch {
            if ($process.HasExited) {
                throw "API exited before readiness with code $($process.ExitCode)"
            }
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) {
        throw "API did not become ready"
    }

    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz"
    if ($health.status -ne "ok" -or $health.build_id -ne $manifest.build_id) {
        throw "Unexpected health response"
    }

    $query = [Uri]::EscapeDataString($searchTarget.name)
    $search = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/games/search?q=$query"
    if ($search.games.appid -notcontains $searchTarget.appid) {
        throw "Search did not return artifact game"
    }

    $request = @{
        seeds = @(@{ appid = $seedRecord.source_appid; weight = 1.0 })
        intent = @{
            lane_weights = @{
                mechanics = 1.0
                narrative = 1.0
                vibe = 1.0
                structure_loop = 1.0
            }
            include = @()
            exclude = @()
            text = $null
        }
        limit = 10
    } | ConvertTo-Json -Depth 5
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/recommendations" -Method Post -ContentType "application/json" -Body $request
    $rankingValid = if ($expectedMode -eq "candidate_graph") {
        $response.results[0].game.appid -eq $expectedTop.appid
    } else {
        $response.results.Count -gt 0 -and $response.results[0].game.appid -ne $seedRecord.source_appid
    }
    if (
        $response.build_id -ne $manifest.build_id -or
        $response.retrieval.mode -ne $expectedMode -or
        -not $rankingValid
    ) {
        throw "Recommendation smoke response was invalid"
    }

    if ($LoadOutput) {
        & uv run -- nextsteam-pipeline benchmark-api `
            --base-url "http://127.0.0.1:$Port" `
            --artifact $artifact `
            --output $LoadOutput `
            --requests $LoadRequests `
            --concurrency $LoadConcurrency
        if ($LASTEXITCODE -ne 0) {
            throw "API load benchmark failed"
        }
    }
} finally {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}
