[CmdletBinding()]
param(
    [switch]$RequireAzure,
    [switch]$RequireFabricAccess
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Test-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing '$Name'. $InstallHint"
    }
    Write-Host "[ok] $Name"
}

Test-Command python "Install Python 3.10 or later."
Test-Command az "Install Azure CLI."

$version = & python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ([version]$version -lt [version]"3.10") {
    throw "Python 3.10 or later is required; found $version."
}
Write-Host "[ok] Python $version"

& python -c "import duckdb, jsonschema, pyarrow, requests, azure.identity"
if ($LASTEXITCODE -ne 0) {
    throw "Python dependencies are missing. Run: python -m pip install -r `"$root\requirements.txt`""
}
Write-Host "[ok] Python dependencies"

if ($RequireAzure -or $RequireFabricAccess) {
    & az account show --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI authentication is required. Run 'az login' or use workload identity/service principal login in CI."
    }
    Write-Host "[ok] Azure CLI session"
}

if ($RequireFabricAccess) {
    $workspaceId = (Get-Content "$root\config\lab.json" -Raw | ConvertFrom-Json).workspace.id
    $token = & az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $token) {
        throw "Unable to acquire a Fabric API token from the current Azure CLI session."
    }
    try {
        $response = Invoke-RestMethod `
            -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId" `
            -Headers @{ Authorization = "Bearer $token" } `
            -Method Get
        Write-Host "[ok] Fabric workspace access: $($response.displayName) ($workspaceId)"
    }
    catch {
        throw "Fabric workspace access failed for ${workspaceId}: $($_.Exception.Message)"
    }
}

Write-Host "Preflight passed."
