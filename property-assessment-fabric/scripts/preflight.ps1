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
$hasAzureCli = $null -ne (Get-Command az -ErrorAction SilentlyContinue)
$clientCredentialNames = @("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
$configuredClientCredentials = @(
    $clientCredentialNames | Where-Object {
        -not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_, "Process"))
    }
)
if ($configuredClientCredentials.Count -gt 0 -and $configuredClientCredentials.Count -lt $clientCredentialNames.Count) {
    $missing = @(
        $clientCredentialNames | Where-Object {
            [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_, "Process"))
        }
    )
    throw "Incomplete Fabric client credentials. Missing process environment variables: $($missing -join ', ')"
}
$hasClientCredentials = $configuredClientCredentials.Count -eq $clientCredentialNames.Count

$version = & python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
if ([version]$version -lt [version]"3.10") {
    throw "Python 3.10 or later is required; found $version."
}
Write-Host "[ok] Python $version"

& python -c "import duckdb, jsonschema, pyarrow, requests, azure.identity, azure.storage.filedatalake"
if ($LASTEXITCODE -ne 0) {
    throw "Python dependencies are missing. Run: python -m pip install -r `"$root\requirements.txt`""
}
Write-Host "[ok] Python dependencies"

if ($RequireAzure) {
    if (-not $hasAzureCli) {
        throw "Azure source provisioning requires Azure CLI. Install 'az' or run only Fabric deployment with client credentials."
    }
    & az account show --output none
    if ($LASTEXITCODE -ne 0) {
        throw "Azure CLI authentication is required for Azure source provisioning."
    }
    Write-Host "[ok] Azure CLI session"
}

if ($RequireFabricAccess) {
    if (-not $hasAzureCli -and -not $hasClientCredentials) {
        throw "Fabric access requires either an authenticated Azure CLI or complete process environment variables AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET."
    }
    & python "$root\scripts\fabric_deploy.py" --check-access
    if ($LASTEXITCODE -ne 0) {
        throw "Fabric workspace access check failed."
    }
    $mode = if ($hasClientCredentials) { "OAuth client credentials" } else { "Azure CLI" }
    Write-Host "[ok] Fabric workspace access using $mode"
}

Write-Host "Preflight passed."
