# Restore MongoDB from mongodump archive (sample verification — use on staging only).
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupArchive,
    [string]$ComposeFile = "docker-compose.production.yml",
    [string]$EnvFile = ".env.production"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $BackupArchive)) {
    throw "Backup not found: $BackupArchive"
}

Write-Host "Restoring MongoDB from $BackupArchive (drops are NOT performed; archive overwrites collections in target DB)"
Get-Content -Path $BackupArchive -AsByteStream -ReadCount 0 | docker compose -f $ComposeFile --env-file $EnvFile exec -T mongodb sh -c `
    'mongorestore --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip --drop'
Write-Host "Mongo restore finished."
