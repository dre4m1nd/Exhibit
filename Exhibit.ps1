# Launch the Exhibit terminal agent.
param(
    [switch]$Rebuild,
    [string]$Repo = ""
)

$ErrorActionPreference = "Stop"
$LaunchDir = (Get-Location).Path
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$TargetRepo = if ($Repo) {
    [System.IO.Path]::GetFullPath($Repo, $LaunchDir)
} else {
    $LaunchDir
}
if (-not (Test-Path -LiteralPath $TargetRepo -PathType Container)) {
    Write-Error "目标目录不存在: $TargetRepo"
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "缺少 .venv，请先运行: python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

if (-not (Test-Path "tui\node_modules")) {
    Write-Error "缺少 tui/node_modules，请先运行: cd tui; npm install"
}

$DistRoot = Join-Path $Root "tui\dist"
$DistMain = Join-Path $DistRoot "main.js"

function Test-NeedsBuild {
    if ($Rebuild) { return $true }
    if (-not (Test-Path $DistMain)) { return $true }
    $builtAt = (Get-Item $DistMain).LastWriteTimeUtc
    $inputs = Get-ChildItem (Join-Path $Root "tui\src") -Recurse -File -Include *.ts, *.tsx
    $inputs += Get-Item (Join-Path $Root "tui\tsconfig.json")
    $inputs += Get-Item (Join-Path $Root "tui\package.json")
    return [bool]($inputs | Where-Object { $_.LastWriteTimeUtc -gt $builtAt })
}

# tsc never deletes output for sources that were removed, so prune stale modules.
function Remove-StaleOutput {
    if (-not (Test-Path $DistRoot)) { return }
    $srcRoot = Join-Path $Root "tui\src"
    Get-ChildItem $DistRoot -Recurse -File -Filter *.js | ForEach-Object {
        $relative = $_.FullName.Substring($DistRoot.Length + 1)
        # A .tsx source compiles to a .js output, so match on the bare name.
        $name = [System.IO.Path]::GetFileNameWithoutExtension($relative)
        $folder = [System.IO.Path]::GetDirectoryName($relative)
        $stem = if ($folder) { Join-Path $folder $name } else { $name }
        $ts = Join-Path $srcRoot ($stem + ".ts")
        $tsx = Join-Path $srcRoot ($stem + ".tsx")
        if (-not (Test-Path $ts) -and -not (Test-Path $tsx)) {
            Remove-Item -LiteralPath $_.FullName -Force
            Write-Host "  清理过期产物: $relative" -ForegroundColor DarkGray
        }
    }
}

if (Test-NeedsBuild) {
    Write-Host "TUI 源码有更新，正在编译..." -ForegroundColor Yellow
    Push-Location tui
    try {
        node node_modules\typescript\bin\tsc -p tsconfig.json
        if ($LASTEXITCODE -ne 0) {
            throw "TUI 编译失败（tsc exit $LASTEXITCODE），请先修复类型错误"
        }
    } finally {
        Pop-Location
    }
    Remove-StaleOutput
}

node tui\dist\main.js --repo-path $TargetRepo
