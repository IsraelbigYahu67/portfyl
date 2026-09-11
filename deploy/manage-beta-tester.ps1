[CmdletBinding(SupportsShouldProcess)]
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
    [string]$JobName = "portfyl-beta-admin",

    # Cloudflare Access reusable policy this script keeps in sync with
    # `beta_invites`. Defaults match the live IDs recorded in
    # docs/operations/private-beta-access.md; override only if that policy is
    # ever recreated.
    [string]$CloudflareAccountId = $env:CLOUDFLARE_ACCOUNT_ID,
    [string]$CloudflareApiToken = $env:CLOUDFLARE_API_TOKEN,
    [string]$CloudflarePolicyId = "b6f0c838-536a-4606-aa7c-b7191a0d681f",

    # list-only: also fetch the Cloudflare policy and report drift against
    # beta_invites, instead of only printing the database's view.
    [switch]$CheckCloudflare
)

$ErrorActionPreference = "Stop"

if ($Action -ne "list" -and [string]::IsNullOrWhiteSpace($Email)) {
    throw "-Email is required for '$Action'."
}

$cloudflareConfigured = -not ([string]::IsNullOrWhiteSpace($CloudflareAccountId)) `
    -and -not ([string]::IsNullOrWhiteSpace($CloudflareApiToken))

# ---------------------------------------------------------------------------
# Cloudflare Access: keep the reusable "Portfyl private beta testers" policy's
# exact-email include list in sync with beta_invites. See
# docs/operations/private-beta-access.md -- this policy must never gain an
# Everyone, Login Methods, or e-mail-domain-wide rule.
# ---------------------------------------------------------------------------

function Get-CloudflareAccessPolicy {
    param([string]$AccountId, [string]$ApiToken, [string]$PolicyId)
    $uri = "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/policies/$PolicyId"
    $response = Invoke-RestMethod -Method Get -Uri $uri -Headers @{
        Authorization = "Bearer $ApiToken"
    }
    if (-not $response.success) {
        throw "Cloudflare API rejected the policy read: $($response.errors | ConvertTo-Json -Compress)"
    }
    return $response.result
}

function Set-CloudflareAccessPolicy {
    param([string]$AccountId, [string]$ApiToken, [string]$PolicyId, $Policy)
    $uri = "https://api.cloudflare.com/client/v4/accounts/$AccountId/access/policies/$PolicyId"
    # Cloudflare's policy PUT replaces the whole object -- round-trip every
    # field exactly as GET returned it except the one array this script owns.
    $body = @{
        name             = $Policy.name
        decision         = $Policy.decision
        include          = $Policy.include
        exclude          = $Policy.exclude
        require          = $Policy.require
        session_duration = $Policy.session_duration
    } | ConvertTo-Json -Depth 10
    $response = Invoke-RestMethod -Method Put -Uri $uri -Headers @{
        Authorization  = "Bearer $ApiToken"
        "Content-Type" = "application/json"
    } -Body $body
    if (-not $response.success) {
        throw "Cloudflare API rejected the policy update: $($response.errors | ConvertTo-Json -Compress)"
    }
    return $response.result
}

function Get-PolicyEmails {
    param($Policy)
    # Each exact-email Include rule is shaped {"email": {"email": "x@y.com"}}.
    # Other rule kinds (everyone, email_domain, ...) are left untouched and
    # simply pass through Set-CloudflareAccessPolicy unmodified.
    return @($Policy.include | Where-Object { $_.email -and $_.email.email } | ForEach-Object { $_.email.email.ToLowerInvariant() })
}

function Add-CloudflareBetaEmail {
    param([string]$AccountId, [string]$ApiToken, [string]$PolicyId, [string]$NormalizedEmail)
    $policy = Get-CloudflareAccessPolicy -AccountId $AccountId -ApiToken $ApiToken -PolicyId $PolicyId
    $existing = Get-PolicyEmails -Policy $policy
    if ($existing -contains $NormalizedEmail) {
        Write-Host "Cloudflare Access already includes $NormalizedEmail; leaving the policy unchanged."
        return
    }
    if ($PSCmdlet.ShouldProcess("Cloudflare Access policy $PolicyId", "add $NormalizedEmail")) {
        $newInclude = @($policy.include) + @(@{ email = @{ email = $NormalizedEmail } })
        $policy.include = $newInclude
        Set-CloudflareAccessPolicy -AccountId $AccountId -ApiToken $ApiToken -PolicyId $PolicyId -Policy $policy | Out-Null
        Write-Host "Cloudflare Access: added $NormalizedEmail to the private beta testers policy."
    }
}

function Remove-CloudflareBetaEmail {
    param([string]$AccountId, [string]$ApiToken, [string]$PolicyId, [string]$NormalizedEmail)
    $policy = Get-CloudflareAccessPolicy -AccountId $AccountId -ApiToken $ApiToken -PolicyId $PolicyId
    $existing = Get-PolicyEmails -Policy $policy
    if ($existing -notcontains $NormalizedEmail) {
        Write-Host "Cloudflare Access does not include $NormalizedEmail; leaving the policy unchanged."
        return
    }
    if ($PSCmdlet.ShouldProcess("Cloudflare Access policy $PolicyId", "remove $NormalizedEmail")) {
        $policy.include = @($policy.include | Where-Object { -not ($_.email -and $_.email.email -and $_.email.email.ToLowerInvariant() -eq $NormalizedEmail) })
        Set-CloudflareAccessPolicy -AccountId $AccountId -ApiToken $ApiToken -PolicyId $PolicyId -Policy $policy | Out-Null
        Write-Host "Cloudflare Access: removed $NormalizedEmail from the private beta testers policy."
    }
}

# ---------------------------------------------------------------------------
# beta_invites (PostgreSQL, via the one-off Cloud Run Job) -- unchanged.
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Keep Cloudflare in sync with the database write that just succeeded.
# ---------------------------------------------------------------------------

if ($Action -in @("invite", "revoke")) {
    $normalizedEmail = $Email.Trim().ToLowerInvariant()
    if (-not $cloudflareConfigured) {
        Write-Warning (
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are not set -- " +
            "beta_invites was updated but the Cloudflare Access policy was " +
            "NOT. Manually $(if ($Action -eq 'invite') { 'add' } else { 'remove' }) " +
            "the exact e-mail rule for $normalizedEmail in the 'Portfyl private " +
            "beta testers' policy (see docs/operations/private-beta-access.md)."
        )
    }
    elseif ($Action -eq "invite") {
        Add-CloudflareBetaEmail -AccountId $CloudflareAccountId -ApiToken $CloudflareApiToken -PolicyId $CloudflarePolicyId -NormalizedEmail $normalizedEmail
    }
    else {
        Remove-CloudflareBetaEmail -AccountId $CloudflareAccountId -ApiToken $CloudflareApiToken -PolicyId $CloudflarePolicyId -NormalizedEmail $normalizedEmail
    }
}

if ($Action -eq "list" -and $CheckCloudflare) {
    if (-not $cloudflareConfigured) {
        Write-Warning "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are not set -- cannot check Cloudflare Access for drift."
    }
    else {
        $policy = Get-CloudflareAccessPolicy -AccountId $CloudflareAccountId -ApiToken $CloudflareApiToken -PolicyId $CloudflarePolicyId
        $cloudflareEmails = Get-PolicyEmails -Policy $policy
        Write-Host ""
        Write-Host "Cloudflare Access 'Portfyl private beta testers' currently includes:"
        $cloudflareEmails | Sort-Object | ForEach-Object { Write-Host "  $_" }
        Write-Host ""
        Write-Host "Compare this list by hand against the beta_invites rows printed above;"
        Write-Host "any e-mail on one side but not the other is drift between the two systems."
    }
}
