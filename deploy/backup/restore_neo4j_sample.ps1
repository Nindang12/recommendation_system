# Restore Neo4j from neo4j-admin dump directory (staging verification only).
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir,
    [string]$ComposeFile = "docker-compose.production.yml",
    [string]$EnvFile = ".env.production"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $BackupDir)) {
    throw "Backup dir not found: $BackupDir"
}

Write-Host "Copying dump into neo4j container..."
docker compose -f $ComposeFile --env-file $EnvFile cp $BackupDir "neo4j:/tmp/neo4j-restore"
Write-Host "Stopping database, loading dump, starting..."
docker compose -f $ComposeFile --env-file $EnvFile exec -T neo4j neo4j-admin database load neo4j `
    --from-path=/tmp/neo4j-restore --overwrite-destination=true
Write-Host "Neo4j restore finished."
