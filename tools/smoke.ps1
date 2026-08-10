param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactDir,
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifact = (Resolve-Path -LiteralPath $ArtifactDir).Path

& cargo build --locked -p api --manifest-path "$repoRoot/Cargo.toml"
if ($LASTEXITCODE -ne 0) {
    throw "API build failed"
}

$environment = @{
    ARTIFACT_DIR = $artifact
    ALLOW_FIXTURE_ARTIFACTS = "1"
    API_BIND = "127.0.0.1:$Port"
    RUST_LOG = "warn"
}
$binary = Join-Path $repoRoot "target/debug/api.exe"
$process = Start-Process -FilePath $binary -PassThru -NoNewWindow -Environment $environment

try {
    $ready = $false
    foreach ($attempt in 1..40) {
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$Port/readyz" | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) {
        throw "API did not become ready"
    }

    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz"
    if ($health.status -ne "ok" -or $health.build_id -ne "synthetic-fixture-v1") {
        throw "Unexpected health response"
    }

    $search = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/v1/games/search?q=Fixture"
    if ($search.games.Count -ne 2) {
        throw "Search did not return fixture games"
    }

    $request = @{
        seeds = @(@{ appid = 900001; weight = 1.0 })
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
    if ($response.build_id -ne "synthetic-fixture-v1" -or $response.results[0].game.appid -ne 900002) {
        throw "Recommendation smoke response was invalid"
    }
} finally {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}
