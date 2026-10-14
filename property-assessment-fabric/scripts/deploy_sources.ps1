[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-property-assessment-lab",
    [string]$Location = "canadacentral",
    [string]$CosmosLocation = "eastus2",
    [string]$SubscriptionId,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ($SubscriptionId) {
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) { throw "Unable to select subscription." }
}
$account = az account show --output json | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "Azure CLI authentication is required." }
$suffix = ($account.id -replace "-", "").Substring(0, 8).ToLowerInvariant()
$names = [ordered]@{
    resourceGroup = $ResourceGroup
    sqlServer = "pa-sql-$suffix"
    sqlDatabase = "property-assessment"
    cosmosAccount = "pacosmos$suffix"
    cosmosDatabase = "property-profiles"
    cosmosContainer = "properties"
    storageAccount = "pastorage$suffix"
    fileSystem = "assessment-data"
}
$names | ConvertTo-Json
if ($PlanOnly) { return }

function Invoke-Az {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    az @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Azure CLI command failed: az $($Arguments -join ' ')" }
}

Invoke-Az group create --name $ResourceGroup --location $Location --tags solution=property-assessment-fabric data=synthetic --output none

$principal = az ad signed-in-user show --output json 2>$null | ConvertFrom-Json
if (-not $principal) {
    throw "Interactive source provisioning needs a signed-in user for the initial SQL Entra administrator. In CI, precreate the SQL server with an Entra group administrator, then rerun seeding with service-principal database permissions."
}

if (-not (az sql server show -g $ResourceGroup -n $names.sqlServer -o none 2>$null)) {
    Invoke-Az sql server create -g $ResourceGroup -n $names.sqlServer -l $Location --enable-ad-only-auth `
        --external-admin-principal-type User --external-admin-name $principal.userPrincipalName `
        --external-admin-sid $principal.id --enable-public-network true --output none
}
Invoke-Az sql db create -g $ResourceGroup -s $names.sqlServer -n $names.sqlDatabase `
    --service-objective Basic --max-size 2GB --backup-storage-redundancy Local --output none
Invoke-Az sql server firewall-rule create -g $ResourceGroup -s $names.sqlServer -n AllowAzureServices `
    --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 --output none

if (-not (az cosmosdb show -g $ResourceGroup -n $names.cosmosAccount -o none 2>$null)) {
    Invoke-Az cosmosdb create -g $ResourceGroup -n $names.cosmosAccount `
        --locations regionName=$CosmosLocation failoverPriority=0 isZoneRedundant=False `
        --default-consistency-level Session --output none
}
Invoke-Az cosmosdb sql database create -g $ResourceGroup -a $names.cosmosAccount -n $names.cosmosDatabase --output none
if (-not (az cosmosdb sql container show -g $ResourceGroup -a $names.cosmosAccount -d $names.cosmosDatabase -n $names.cosmosContainer -o none 2>$null)) {
    Invoke-Az cosmosdb sql container create -g $ResourceGroup -a $names.cosmosAccount -d $names.cosmosDatabase `
        -n $names.cosmosContainer -p /neighborhoodId --throughput 400 --output none
}

if (-not (az storage account show -g $ResourceGroup -n $names.storageAccount -o none 2>$null)) {
    Invoke-Az storage account create -g $ResourceGroup -n $names.storageAccount -l $Location `
        --sku Standard_LRS --kind StorageV2 --hns true --allow-blob-public-access false `
        --min-tls-version TLS1_2 --https-only true --output none
}
$storageId = az storage account show -g $ResourceGroup -n $names.storageAccount --query id -o tsv
Invoke-Az role assignment create --assignee-object-id $principal.id --assignee-principal-type User `
    --role "Storage Blob Data Contributor" --scope $storageId --output none
Invoke-Az storage fs create -n $names.fileSystem --account-name $names.storageAccount --auth-mode login --output none

$statePath = Join-Path (Split-Path -Parent $PSScriptRoot) ".state\azure-sources.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $statePath) | Out-Null
$names | ConvertTo-Json | Set-Content -Encoding utf8 $statePath
Write-Host "Azure source shell deployed. Use seed_sources.ps1 after role propagation."

