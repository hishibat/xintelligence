# =============================================================================
# sync_to_xintelligence.ps1
# -----------------------------------------------------------------------------
# Dual-repo sync helper.
#
# This project lives in TWO places:
#   primary:   hishibat/company  (path: Content_Production/x-intelligence/)
#              ↑ 開発はこちらで commit
#   mirror:    hishibat/xintelligence (root に展開)
#              ↑ 公開・スタンドアロン参照用、履歴を保ったまま同期
#
# このスクリプトは company 側でコミット済みの差分を、subtree split で再抽出して
# xintelligence remote の `main` に push します。
#
# 使い方 (PowerShell):
#   cd C:\Users\Hideyuki Shibata\workspace\company\Content_Production\x-intelligence
#   .\scripts\sync_to_xintelligence.ps1            # 通常 push
#   .\scripts\sync_to_xintelligence.ps1 -DryRun    # split のみで push しない
#
# 前提:
#   - workspace/company の git remote `xintelligence` が
#     https://github.com/hishibat/xintelligence.git に向いていること
#   - 同期したい commit が origin (company) に push 済みであること推奨
#     (subtree split は HEAD を見るので、未 push の commit も同期されます)
# =============================================================================

param(
    [switch]$DryRun
)

# IMPORTANT: do NOT set $ErrorActionPreference = "Stop" here.
# git writes progress to stderr (e.g. "1/25 (0) [0]") even on success.
# In PowerShell 5.1, ErrorActionPreference=Stop combined with stderr
# output from a native exe raises NativeCommandError and aborts the
# script BEFORE we can inspect $LASTEXITCODE. We rely on explicit
# $LASTEXITCODE checks after each git invocation instead.

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Prefix   = "Content_Production/x-intelligence"
$TempBranch = "xintelligence-sync-$(Get-Date -Format 'yyyyMMddHHmmss')"
$RemoteName = "xintelligence"
$RemoteBranch = "main"

Write-Host "=== xintelligence dual-repo sync ===" -ForegroundColor Cyan
Write-Host "RepoRoot     : $RepoRoot"
Write-Host "Prefix       : $Prefix"
Write-Host "Remote       : $RemoteName -> $RemoteBranch"
Write-Host "Temp branch  : $TempBranch"
Write-Host "DryRun       : $DryRun"
Write-Host ""

Push-Location $RepoRoot
try {
    # 1) Verify remote exists
    $remotes = git remote
    if ($LASTEXITCODE -ne 0) {
        Write-Error "git remote listing failed (exit $LASTEXITCODE)"
        exit 1
    }
    if ($remotes -notcontains $RemoteName) {
        Write-Error "git remote '$RemoteName' is not configured. Run: git remote add $RemoteName https://github.com/hishibat/xintelligence.git"
        exit 1
    }

    # 2) Working tree must be clean enough — warn if there are unstaged
    #    changes inside the prefix (subtree split sees HEAD, so unstaged
    #    edits would not be synced).
    $dirtyInPrefix = git status --short -- $Prefix
    if ($dirtyInPrefix) {
        Write-Warning "Unstaged changes detected inside $Prefix — these will NOT be synced:"
        Write-Warning $dirtyInPrefix
        Write-Warning "Commit them first if you want them included."
    }

    # 3) Subtree split — extract the prefix history into a temp branch.
    # `git subtree split` writes progress ("N/M (X) [Y]") to stderr even on
    # success — that's normal. We check $LASTEXITCODE to decide success/fail.
    Write-Host "[1/2] git subtree split --prefix=$Prefix HEAD -b $TempBranch" -ForegroundColor Yellow
    git subtree split --prefix=$Prefix HEAD -b $TempBranch
    if ($LASTEXITCODE -ne 0) {
        Write-Error "subtree split failed (exit $LASTEXITCODE)"
        exit 1
    }

    $newHead = (git rev-parse $TempBranch).Trim()
    Write-Host "    split HEAD = $newHead"

    # 4) Push (unless dry-run)
    if ($DryRun) {
        Write-Host "[2/2] DryRun: skipping push. Branch '$TempBranch' left in place for inspection." -ForegroundColor Magenta
        Write-Host "       Cleanup with: git branch -D $TempBranch"
    }
    else {
        Write-Host "[2/2] git push $RemoteName $TempBranch`:$RemoteBranch" -ForegroundColor Yellow
        git push $RemoteName "$TempBranch`:$RemoteBranch"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "git push failed (exit $LASTEXITCODE). Branch '$TempBranch' left in place for retry."
            exit 1
        }

        # 5) Cleanup temp branch on success
        Write-Host "    cleaning up local temp branch '$TempBranch'"
        git branch -D $TempBranch | Out-Null

        Write-Host ""
        Write-Host "Done. Synced to https://github.com/hishibat/xintelligence (branch $RemoteBranch)" -ForegroundColor Green
    }
}
finally {
    Pop-Location
}
