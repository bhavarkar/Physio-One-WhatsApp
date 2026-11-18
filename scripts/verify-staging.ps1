<#
.SYNOPSIS
    Controlled Staging Verification Runner for Physio One WhatsApp AI Platform.
.DESCRIPTION
    Executes automated local pre-flight verifications (backend pytest, frontend Jest,
    TypeScript, Next.js build, Docker Compose, Terraform) and optional read-only
    Google Cloud staging infrastructure inspections.
    Compatible with Windows PowerShell 5.1 and PowerShell 7+.
.PARAMETER ProjectId
    Optional Google Cloud Project ID for read-only cloud inspection.
.PARAMETER Region
    Google Cloud region. Defaults to 'asia-south1'.
.PARAMETER LocalOnly
    Perform only local validations without probing cloud infrastructure.
.PARAMETER CloudCheck
    Perform read-only inspection of live Google Cloud staging resources (requires ProjectId).
.PARAMETER VerboseOutput
    Display detailed output from verification commands.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Region = "asia-south1",

    [Parameter(Mandatory = $false)]
    [switch]$LocalOnly,

    [Parameter(Mandatory = $false)]
    [switch]$CloudCheck,

    [Parameter(Mandatory = $false)]
    [switch]$VerboseOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Auto-load User PATH entries if missing from current process environment
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath) {
    foreach ($p in ($userPath -split ';')) {
        if ($p) {
            $exists = $false
            try { $exists = Test-Path $p -ErrorAction SilentlyContinue } catch { $exists = $false }
            if ($exists -and ($env:PATH -split ';' -notcontains $p)) {
                $env:PATH = "$p;$env:PATH"
            }
        }
    }
}

function Write-CheckHeader {
    param([string]$Title)
    Write-Host "`n[CHECK] $Title" -ForegroundColor Cyan
}

function Write-CheckPass {
    param([string]$Message)
    Write-Host "  [PASS] $Message" -ForegroundColor Green
}

function Write-CheckFail {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function Write-CheckInfo {
    param([string]$Message)
    Write-Host "  [INFO] $Message" -ForegroundColor Gray
}

$results = [System.Collections.Generic.List[PSObject]]::new()

function Record-Result {
    param([string]$CheckName, [string]$Status, [string]$Details)
    $results.Add([PSCustomObject]@{
        Check   = $CheckName
        Status  = $Status
        Details = $Details
    })
}

Write-Host "=================================================================" -ForegroundColor White
Write-Host " PHYSIO ONE WHATSAPP AI PLATFORM — STAGING VERIFICATION RUNNER  " -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor White

$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $repoRoot

# ------------------------------------------------------------------------------
# LOCAL CHECKS
# ------------------------------------------------------------------------------
Write-CheckHeader "1. Git Repository & Branch State"
try {
    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()
    $statusOut = (& git status --porcelain).Trim()
    $commit = (& git rev-parse --short HEAD).Trim()

    if ($branch -eq "development") {
        Write-CheckPass "Branch is 'development' (commit: $commit)"
        Record-Result "Git Branch" "PASS" "Branch 'development' at $commit"
    }
    else {
        Write-CheckFail "Current branch is '$branch' (expected 'development')"
        Record-Result "Git Branch" "FAIL" "Branch '$branch' instead of 'development'"
    }

    if ([string]::IsNullOrWhiteSpace($statusOut)) {
        Write-CheckPass "Working tree is clean"
        Record-Result "Git Working Tree" "PASS" "Clean working tree"
    }
    else {
        Write-CheckInfo "Working tree has uncommitted modifications"
        Record-Result "Git Working Tree" "WARN" "Modifications present"
    }
}
catch {
    Write-CheckFail "Git inspection failed: $_"
    Record-Result "Git Inspection" "FAIL" "$_"
}

Write-CheckHeader "2. Backend Pytest Suite"
try {
    $pythonExe = Join-Path $repoRoot "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = "python"
    }
    Write-CheckInfo "Running pytest suite..."
    $prevEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $pytestOut = (& cmd.exe /c "`"$pythonExe`" -m pytest backend\tests -q" 2>&1) | Out-String
    $pytestExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEA

    if ($pytestExit -eq 0) {
        $passedLine = ($pytestOut -split "`r?`n" | Select-String -Pattern "passed").Line
        if (-not $passedLine) { $passedLine = "All tests passed" }
        Write-CheckPass "Backend tests passed: $passedLine"
        Record-Result "Backend Tests" "PASS" $passedLine
    }
    else {
        Write-CheckFail "Backend tests failed with exit code $pytestExit"
        Record-Result "Backend Tests" "FAIL" $pytestOut
    }
}
catch {
    Write-CheckFail "Backend test execution failed: $_"
    Record-Result "Backend Tests" "FAIL" "$_"
}

Write-CheckHeader "3. Frontend Jest & TypeScript Typecheck"
try {
    Write-CheckInfo "Running Jest test suites..."
    $prevEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $jestOut = (& cmd.exe /c "npm --prefix frontend test -- --passWithNoTests" 2>&1) | Out-String
    $jestExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEA

    if ($jestExit -eq 0) {
        Write-CheckPass "Frontend Jest tests passed cleanly"
        Record-Result "Frontend Tests" "PASS" "All Jest suites passed"
    }
    else {
        Write-CheckFail "Frontend Jest tests failed"
        Record-Result "Frontend Tests" "FAIL" $jestOut
    }

    Write-CheckInfo "Running TypeScript typecheck..."
    $prevEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $tscOut = (& cmd.exe /c "npm --prefix frontend run typecheck" 2>&1) | Out-String
    $tscExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEA

    if ($tscExit -eq 0) {
        Write-CheckPass "TypeScript compilation: 0 errors"
        Record-Result "TypeScript Typecheck" "PASS" "0 errors"
    }
    else {
        Write-CheckFail "TypeScript typecheck failed"
        Record-Result "TypeScript Typecheck" "FAIL" $tscOut
    }
}
catch {
    Write-CheckFail "Frontend verification failed: $_"
    Record-Result "Frontend Checks" "FAIL" "$_"
}

Write-CheckHeader "4. Next.js Production Build"
try {
    Write-CheckInfo "Running Next.js production build..."
    $prevEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $buildOut = (& cmd.exe /c "npm --prefix frontend run build" 2>&1) | Out-String
    $buildExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEA

    if ($buildExit -eq 0) {
        Write-CheckPass "Next.js production build succeeded"
        Record-Result "Next.js Build" "PASS" "Compiled cleanly"
    }
    else {
        Write-CheckFail "Next.js production build failed"
        Record-Result "Next.js Build" "FAIL" $buildOut
    }
}
catch {
    Write-CheckFail "Build execution error: $_"
    Record-Result "Next.js Build" "FAIL" "$_"
}

Write-CheckHeader "5. Terraform Staging IaC"
try {
    $tfExe = "terraform"
    $infraDir = Join-Path $repoRoot "infra\staging"
    Set-Location $infraDir

    Write-CheckInfo "Checking Terraform formatting..."
    & $tfExe fmt -check
    if ($LASTEXITCODE -eq 0) {
        Write-CheckPass "Terraform format check passed"
        Record-Result "Terraform Format" "PASS" "Clean formatting"
    }
    else {
        Write-CheckFail "Terraform format check failed"
        Record-Result "Terraform Format" "FAIL" "Formatting required"
    }

    Write-CheckInfo "Validating Terraform configuration..."
    $valOut = & $tfExe validate 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-CheckPass "Terraform configuration is valid"
        Record-Result "Terraform Validate" "PASS" "Valid configuration"
    }
    else {
        Write-CheckFail "Terraform validate failed: $valOut"
        Record-Result "Terraform Validate" "FAIL" ($valOut | Out-String)
    }
}
catch {
    Write-CheckFail "Terraform validation error: $_"
    Record-Result "Terraform Validate" "FAIL" "$_"
}
finally {
    Set-Location $repoRoot
}

Write-CheckHeader "6. Docker Compose Environment"
try {
    Write-CheckInfo "Checking Docker Compose configuration..."
    $prevEA = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $cfgOut = (& cmd.exe /c "docker compose config" 2>&1) | Out-String
    $cfgExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEA

    if ($cfgExit -eq 0) {
        Write-CheckPass "Docker Compose configuration is valid"
        Record-Result "Docker Compose Config" "PASS" "Configuration valid"
    }
    else {
        Write-CheckFail "Docker Compose configuration error"
        Record-Result "Docker Compose Config" "FAIL" $cfgOut
    }
}
catch {
    Write-CheckFail "Docker inspection failed: $_"
    Record-Result "Docker Compose Config" "FAIL" "$_"
}

# ------------------------------------------------------------------------------
# OPTIONAL CLOUD READ-ONLY CHECKS
# ------------------------------------------------------------------------------
if ($CloudCheck -and [string]::IsNullOrWhiteSpace($ProjectId)) {
    Write-CheckFail "ProjectId must be specified when using -CloudCheck."
    Record-Result "Cloud Checks" "FAIL" "Missing ProjectId parameter"
}
elseif ($CloudCheck) {
    Write-CheckHeader "7. Read-Only Google Cloud Staging Health Checks"
    Write-CheckInfo "Target GCP Project: $ProjectId"
    Write-CheckInfo "Target Region:      $Region"

    try {
        # Check Cloud SQL
        Write-CheckInfo "Inspecting Cloud SQL instance 'physio-staging-pg'..."
        $sqlState = & gcloud sql instances describe physio-staging-pg --format="value(state)" 2>$null
        if ($sqlState -eq "RUNNABLE") {
            Write-CheckPass "Cloud SQL is RUNNABLE"
            Record-Result "Cloud SQL State" "PASS" "RUNNABLE"
        }
        else {
            Write-CheckInfo "Cloud SQL state: $(if ($sqlState) { $sqlState } else { 'Not provisioned' })"
            Record-Result "Cloud SQL State" "INFO" "$sqlState"
        }

        # Check Cloud Run API
        Write-CheckInfo "Inspecting Cloud Run service 'physio-staging-api'..."
        $apiUrl = (& gcloud run services describe physio-staging-api --region=$Region --format="value(status.url)" 2>$null).Trim()
        if (-not [string]::IsNullOrWhiteSpace($apiUrl)) {
            Write-CheckPass "Cloud Run API URL: $apiUrl"
            Record-Result "Cloud Run API" "PASS" $apiUrl

            # Probe health
            Write-CheckInfo "Probing API health endpoint: $apiUrl/health"
            try {
                $hp = Invoke-RestMethod -Uri "$apiUrl/health" -Method Get -TimeoutSec 10
                if ($hp.status -eq "healthy") {
                    Write-CheckPass "API /health probe: healthy"
                    Record-Result "API Health Probe" "PASS" "healthy"
                }
                else {
                    Write-CheckFail "API /health probe returned unexpected: $($hp | ConvertTo-Json -Compress)"
                    Record-Result "API Health Probe" "FAIL" "Unhealthy"
                }
            }
            catch {
                Write-CheckFail "API /health probe failed: $_"
                Record-Result "API Health Probe" "FAIL" "$_"
            }
        }
        else {
            Write-CheckInfo "Cloud Run API service not yet deployed."
            Record-Result "Cloud Run API" "INFO" "Not deployed"
        }

        # Check Schedulers state
        Write-CheckInfo "Inspecting Cloud Scheduler jobs..."
        $jobsOut = & gcloud scheduler jobs list --location=$Region --format="value(name,state)" 2>$null
        if ($jobsOut) {
            Write-CheckPass "Schedulers inspected:`n$jobsOut"
            Record-Result "Schedulers State" "PASS" "$jobsOut"
        }
        else {
            Write-CheckInfo "No schedulers currently provisioned."
            Record-Result "Schedulers State" "INFO" "None provisioned"
        }
    }
    catch {
        Write-CheckFail "Cloud inspection failed: $_"
        Record-Result "Cloud Checks" "FAIL" "$_"
    }
}

# ------------------------------------------------------------------------------
# SUMMARY REPORT
# ------------------------------------------------------------------------------
Write-Host "`n=================================================================" -ForegroundColor White
Write-Host " VERIFICATION SUMMARY REPORT                                    " -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor White

$hasFailures = $false
foreach ($res in $results) {
    $color = "Green"
    if ($res.Status -eq "FAIL") {
        $color = "Red"
        $hasFailures = $true
    }
    elseif ($res.Status -in @("WARN", "INFO")) {
        $color = "Yellow"
    }

    $chkPadded = $res.Check.PadRight(30)
    $statPadded = "[$($res.Status)]".PadRight(10)
    Write-Host "$chkPadded $statPadded $($res.Details)" -ForegroundColor $color
}

if ($hasFailures) {
    Write-Host "`nResult: VERIFICATION CHECKS CONTAINED FAILURES." -ForegroundColor Red
    exit 1
}
else {
    Write-Host "`nResult: ALL VERIFICATION CHECKS COMPLETED SUCCESSFULLY." -ForegroundColor Green
    exit 0
}
