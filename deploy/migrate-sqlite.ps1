[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$TargetDatabaseUrl,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[^\s@]+@[^\s@]+\.[^\s@]+$')]
    [string]$OwnerEmail,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$backendPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\backend')).Path
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
$venvPython = Join-Path $backendPath '.venv\Scripts\python.exe'
$pythonCommand = if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $venvPython
} else {
    'python'
}

$arguments = @(
    '-m', 'migrations.sqlite_to_postgres',
    '--source', $sourcePath,
    '--target-database-url', $TargetDatabaseUrl,
    '--owner-email', $OwnerEmail
)
if ($DryRun) {
    $arguments += '--dry-run'
}

$previousDatabaseUrl = $env:DATABASE_URL
$hadDatabaseUrl = Test-Path Env:DATABASE_URL
Push-Location -LiteralPath $backendPath
try {
    # The module imports the application models, which require DATABASE_URL.
    # Do not print the environment value or the assembled argument list.
    $env:DATABASE_URL = $TargetDatabaseUrl
    & $pythonCommand @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "SQLite migration exited with code $LASTEXITCODE"
    }
} finally {
    Pop-Location
    if ($hadDatabaseUrl) {
        $env:DATABASE_URL = $previousDatabaseUrl
    } else {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    }
}
