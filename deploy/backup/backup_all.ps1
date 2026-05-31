# Backup khi dùng docker-compose.infra.yml (service tên mongodb, neo4j).
param(
    [string]$ComposeFile = "docker-compose.infra.yml",
    [string]$EnvFile = ".env",
    [string]$OutputRoot = "deploy/backups"
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dest = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "Backing up MongoDB -> $dest/mongo.archive.gz"
docker compose -f $ComposeFile --env-file $EnvFile exec -T mongodb sh -c `
    'mongodump --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip' `
    > (Join-Path $dest "mongo.archive.gz")

Write-Host "Backing up Neo4j -> $dest/neo4j"
docker compose -f $ComposeFile --env-file $EnvFile exec -T neo4j neo4j-admin database dump neo4j --to-path=/tmp/neo4j-dump
docker compose -f $ComposeFile --env-file $EnvFile cp "neo4j:/tmp/neo4j-dump" (Join-Path $dest "neo4j")

Write-Host "Done: $dest"
