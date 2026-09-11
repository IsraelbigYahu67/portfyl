[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("invite", "revoke", "list")]
    [string]$Action,

    [string]$Email,

    [ValidateRange(1, 365)]
    [int]$ExpiresDays = 30,

    [string]$ProjectId = "portfyl-cloud-fstxby",
    [string]$Region = "europe-west1",
    [string]$Service = "portfyl",
    [string]$JobName = "portfyl-beta-admin"
)

$ErrorActionPreference = "Stop"

if ($Action -ne "list" -and [string]::IsNullOrWhiteSpace($Email)) {
    throw "-Email is required for '$Action'."
}

$gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$image = & $gcloud run services describe $Service `
    --project=$ProjectId `
    --region=$Region `
    --format="value(spec.template.spec.containers[0].image)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($image)) {
    throw "Could not resolve the live $Service image."
}

$jobArgs = @("manage_beta.py", $Action)
if ($Action -ne "list") {
    $jobArgs += $Email.Trim().ToLowerInvariant()
}
if ($Action -eq "invite") {
    $jobArgs += @("--expires-days", $ExpiresDays)
}
$encodedArgs = $jobArgs -join ","

& $gcloud run jobs deploy $JobName `
    --project=$ProjectId `
    --region=$Region `
    --image=$image `
    --service-account="portfyl-runtime@$ProjectId.iam.gserviceaccount.com" `
    --set-secrets="DATABASE_URL=portfyl-database-url:latest" `
    --command="python" `
    --args=$encodedArgs `
    --max-retries=0 `
    --task-timeout=120
if ($LASTEXITCODE -ne 0) {
    throw "Beta administration job deployment failed."
}

& $gcloud run jobs execute $JobName `
    --project=$ProjectId `
    --region=$Region `
    --wait
if ($LASTEXITCODE -ne 0) {
    throw "Beta administration job execution failed."
}
