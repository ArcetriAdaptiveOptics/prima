#Requires -Version 5.1
<#
.SYNOPSIS
  Prompt for GitHub credentials used only by this daoEkarus-main clone.

.DESCRIPTION
  Stores auth under .git/ only via http.*.extraheader (Windows-friendly).
  Clears inherited Git Credential Manager for this repo so another account
  (e.g. Menessao) can be used without changing global gh / git auth.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\setup-git-auth.ps1
#>
[CmdletBinding()]
param(
    [string]$RemoteUrl = "https://github.com/Durham-Adaptive-Optics/daoEkarus.git"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot ".git"))) {
    Write-Error "No .git directory in $repoRoot. Run 'git init' first."
}

Write-Host ""
Write-Host "daoEkarus-main - repo-local GitHub auth"
Write-Host "Auth is stored only under .git/ for this clone."
Write-Host ""

if (-not $PSBoundParameters.ContainsKey("RemoteUrl")) {
    $entered = Read-Host "Remote URL [$RemoteUrl]"
    if ($entered.Trim()) { $RemoteUrl = $entered.Trim() }
} else {
    $RemoteUrl = $RemoteUrl.Trim()
}
if (-not $RemoteUrl) {
    Write-Error "Remote URL is required."
}
if ($RemoteUrl -notmatch '^https://github\.com/') {
    Write-Warning "Expected an https://github.com/... URL for this helper."
}

$username = Read-Host "GitHub username"
$username = $username.Trim()
if (-not $username) {
    Write-Error "Username is required."
}

$secure = Read-Host "GitHub Personal Access Token (PAT)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
$token = $token.Trim()
if (-not $token) {
    Write-Error "Token is required."
}

# Disable inherited helpers (system 'manager') for this repo only.
git config --local --unset-all credential.helper 2>$null
git config --local credential.helper ""

# Repo-local Basic auth header (GCM on Windows often ignores store --file=...).
$b64 = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes(('{0}:{1}' -f $username, $token)))
git config --local --unset-all http.https://github.com/.extraheader 2>$null
git config --local http.https://github.com/.extraheader ("AUTHORIZATION: basic {0}" -f $b64)

# Also keep a redacted-friendly backup file (LF) for reference / recovery.
$credPath = Join-Path $repoRoot ".git\credentials"
$credLine = 'https://{0}:{1}@github.com' -f $username, $token
[IO.File]::WriteAllText($credPath, $credLine + "`n")
$aclGrant = '{0}:(R,W)' -f $env:USERNAME
icacls $credPath /inheritance:r /grant:r $aclGrant | Out-Null

$existing = git remote 2>$null
if ($existing -match '(?m)^origin$') {
    git remote set-url origin $RemoteUrl
    Write-Host "Updated origin -> $RemoteUrl"
} else {
    git remote add origin $RemoteUrl
    Write-Host "Added origin -> $RemoteUrl"
}

Write-Host ""
Write-Host "Testing fetch..."
git fetch origin
if ($LASTEXITCODE -ne 0) {
    Write-Error "git fetch failed. Check the URL, username, PAT scopes (repo), and access to that repository."
}

$defaultBranch = git symbolic-ref --short refs/remotes/origin/HEAD 2>$null
if ($defaultBranch) {
    $defaultBranch = $defaultBranch -replace '^origin/', ''
} else {
    foreach ($cand in @("main", "master")) {
        git rev-parse --verify "origin/$cand" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $defaultBranch = $cand; break }
    }
}

if (-not $defaultBranch) {
    Write-Host "Fetch succeeded, but could not detect default branch."
    Write-Host "Set upstream manually, e.g.: git branch --set-upstream-to=origin/main main"
    exit 0
}

Write-Host "Remote default branch: $defaultBranch"
git checkout -f -B $defaultBranch "origin/$defaultBranch"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Could not check out origin/$defaultBranch"
}

Write-Host ""
Write-Host "Done. Tracking origin/$defaultBranch — you can: git pull"
Write-Host 'Auth for this folder only; other repos unchanged.'
