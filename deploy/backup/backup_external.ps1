# Backup MongoDB + Neo4j từ container ĐANG CHẠY SẴN (infra ngoài Phase 9).
param(
    [Parameter(Mandatory = $true)]
    [string]$MongoContainer,
    [Parameter(Mandatory = $true)]
    [string]$Neo4jContainer,
    [string]$MongoUser = "admin",
    [string]$MongoPassword = "password",
    [string]$OutputRoot = "deploy/backups"
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dest = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $dest | Out-Null

Write-Host "Mongo dump from container: $MongoContainer"
docker exec $MongoContainer mongodump `
    --username $MongoUser --password $MongoPassword --authenticationDatabase admin `
    --archive --gzip > (Join-Path $dest "mongo.archive.gz")

Write-Host "Neo4j dump from container: $Neo4jContainer"
docker exec $Neo4jContainer neo4j-admin database dump neo4j --to-path=/tmp/neo4j-dump-$timestamp
docker cp "${Neo4jContainer}:/tmp/neo4j-dump-$timestamp" (Join-Path $dest "neo4j")

Write-Host "Done: $dest"
