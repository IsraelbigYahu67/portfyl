[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [Parameter(Mandatory = $true)]
    [string]$Region,

    [Parameter(Mandatory = $true)]
    [string]$Image,

    [Parameter(Mandatory = $true)]
    [string]$ServiceAccount,

    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrlSecret,

    [string]$JobName = "portfyl-migrate"
)

# Deploys (or updates) a one-shot Cloud Run Job that runs
# `alembic -c backend/alembic.ini upgrade head` against the target database,
# executes it, and waits for completion. The caller must not deploy the
# service revision until this script exits 0 -- see deploy/cloudrun.md
# "Migrate before you deploy". DATABASE_URL is injected from Secret Manager
# (--DatabaseUrlSecret) and is never passed as a plain --set-env-vars value or
# echoed by this script.

$ErrorActionPreference = 'Stop'

Write-Host "Deploying Cloud Run Job '$JobName' from image '$Image' in $Region ($ProjectId)..."

gcloud run jobs deploy $JobName `
    --project $ProjectId `
    --region $Region `
    --image $Image `
    --service-account $ServiceAccount `
    --set-secrets "DATABASE_URL=$($DatabaseUrlSecret):latest" `
    --command "alembic" `
    --args "-c,backend/alembic.ini,upgrade,head" `
    --max-retries 0 `
    --task-timeout 300
if ($LASTEXITCODE -ne 0) {
    throw "gcloud run jobs deploy exited with code $LASTEXITCODE"
}

Write-Host "Executing '$JobName' and waiting for completion..."

gcloud run jobs execute $JobName `
    --project $ProjectId `
    --region $Region `
    --wait
if ($LASTEXITCODE -ne 0) {
    throw "Migration job failed (exit code $LASTEXITCODE) -- inspect logs before deploying the service: gcloud run jobs executions list --job=$JobName --project=$ProjectId --region=$Region"
}

Write-Host "Migration job succeeded. Safe to deploy the service revision now."
