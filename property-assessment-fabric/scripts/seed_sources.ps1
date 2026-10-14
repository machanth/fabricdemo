[CmdletBinding()]
param([string]$StatePath)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $StatePath) { $StatePath = "$root\.state\azure-sources.json" }
if (-not (Test-Path $StatePath)) { throw "Source ownership state not found: $StatePath" }
$state = Get-Content $StatePath -Raw | ConvertFrom-Json

python "$root\scripts\generate_data.py" --scale 240 --seed 20261013
if ($LASTEXITCODE -ne 0) { throw "Data generation failed." }

if (-not (Get-Command sqlcmd -ErrorAction SilentlyContinue)) {
    throw "sqlcmd is required for Azure SQL seeding."
}
sqlcmd -S "$($state.sqlServer).database.windows.net" -d $state.sqlDatabase `
    --authentication-method ActiveDirectoryAzCli -N true -b -i "$root\source\azure-sql\schema.sql"
if ($LASTEXITCODE -ne 0) { throw "Azure SQL schema deployment failed." }
sqlcmd -S "$($state.sqlServer).database.windows.net" -d $state.sqlDatabase `
    --authentication-method ActiveDirectoryAzCli -N true -b -i "$root\data\generated\sql\seed.generated.sql"
if ($LASTEXITCODE -ne 0) { throw "Azure SQL seed failed." }

python "$root\scripts\seed_cosmos.py" `
    --endpoint "https://$($state.cosmosAccount).documents.azure.com:443/" `
    --database $state.cosmosDatabase --container $state.cosmosContainer `
    --file "$root\data\generated\cosmos\property_profiles.json"
if ($LASTEXITCODE -ne 0) { throw "Cosmos seed failed." }

foreach ($file in @("assessment_appeals.json", "assessment_appeals.parquet")) {
    az storage fs file upload --account-name $state.storageAccount --auth-mode login `
        --file-system $state.fileSystem --path "appeals/$file" `
        --source "$root\data\generated\adls\$file" --overwrite true --output none
    if ($LASTEXITCODE -ne 0) { throw "ADLS upload failed for $file." }
}
Write-Host "Synthetic sources seeded."

