param(
    [Parameter(Mandatory = $true)]
    [string]$ExternalProjectPath,

    [Parameter(Mandatory = $true)]
    [string]$BaseRef,

    [string]$IntegrationBranch = ("integration/external-user-" + (Get-Date -Format "yyyy-MM-dd")),
    [string]$TempBranch = ("temp/external-snapshot-" + (Get-Date -Format "yyyy-MM-dd-HHmm")),
    [switch]$SkipCheckoutIntegration,
    [switch]$NoMerge
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $joined = $Args -join " "
    Write-Host ("> git " + $joined) -ForegroundColor Cyan
    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git command failed: git $joined"
    }
}

function Assert-CleanWorkingTree {
    $status = (& git status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read git status."
    }
    if ($status) {
        throw "Working tree is not clean. Commit or stash changes before running this script."
    }
}

$repoRoot = (& git rev-parse --show-toplevel)
if ($LASTEXITCODE -ne 0 -or -not $repoRoot) {
    throw "This script must run inside a git repository."
}

$repoRoot = $repoRoot.Trim()
$externalFullPath = [System.IO.Path]::GetFullPath($ExternalProjectPath)

if (-not (Test-Path -LiteralPath $externalFullPath -PathType Container)) {
    throw "External project path does not exist: $externalFullPath"
}

Assert-CleanWorkingTree

# Verify base reference exists before branch operations.
Invoke-Git -Args @("rev-parse", "--verify", $BaseRef)

$currentBranch = (& git branch --show-current).Trim()
if (-not $currentBranch) {
    throw "Could not detect current branch."
}

$integrationExists = (& git show-ref --verify --quiet ("refs/heads/" + $IntegrationBranch)); $integrationCode = $LASTEXITCODE
if ($integrationCode -eq 0) {
    Write-Host ("Integration branch already exists: " + $IntegrationBranch) -ForegroundColor Yellow
} else {
    Invoke-Git -Args @("branch", $IntegrationBranch, $currentBranch)
}

$tempExists = (& git show-ref --verify --quiet ("refs/heads/" + $TempBranch)); $tempCode = $LASTEXITCODE
if ($tempCode -eq 0) {
    throw "Temp branch already exists: $TempBranch"
}

Invoke-Git -Args @("switch", "-c", $TempBranch, $BaseRef)

Write-Host "> robocopy external snapshot into repository" -ForegroundColor Cyan
$null = & robocopy $externalFullPath $repoRoot /E /XD .git .venv build dist __pycache__ .pytest_cache .mypy_cache
$robocopyExit = $LASTEXITCODE

# Robocopy exit codes lower than 8 are success conditions.
if ($robocopyExit -ge 8) {
    throw "robocopy failed with exit code $robocopyExit"
}

Invoke-Git -Args @("add", "-A")

$hasChanges = (& git status --porcelain)
if (-not $hasChanges) {
    throw "No changes detected after copying external project. Check ExternalProjectPath and BaseRef."
}

$commitMessage = "Import external user snapshot from folder"
Invoke-Git -Args @("commit", "-m", $commitMessage)

if (-not $SkipCheckoutIntegration) {
    Invoke-Git -Args @("switch", $IntegrationBranch)
}

if (-not $NoMerge) {
    Invoke-Git -Args @("merge", $TempBranch)
}

Write-Host "" 
Write-Host "Integration flow completed." -ForegroundColor Green
Write-Host ("Current branch: " + ((& git branch --show-current).Trim())) -ForegroundColor Green
Write-Host ("Temp snapshot branch: " + $TempBranch) -ForegroundColor Green
Write-Host "" 
Write-Host "Next suggested checks:" -ForegroundColor Yellow
Write-Host "1) Run app and smoke test key features."
Write-Host "2) Resolve any merge conflicts if present."
Write-Host "3) Keep temp branch until validation is complete."
