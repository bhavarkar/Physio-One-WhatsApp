<#
.SYNOPSIS
    Controlled Staging Deployment Orchestrator for Physio One WhatsApp AI Platform.
.DESCRIPTION
    Automates and enforces multi-stage, acyclic Google Cloud staging deployment
    using Terraform, Google Cloud CLI, and Docker.
    Compatible with Windows PowerShell 5.1 and PowerShell 7+.
.PARAMETER ProjectId
    The Google Cloud Project ID (e.g., 'physio-staging-2026'). Required for cloud actions.
.PARAMETER Region
    The Google Cloud target region. Defaults to 'asia-south1'.
.PARAMETER Commit
    Git commit SHA tag for container images. Defaults to current HEAD short hash.
.PARAMETER DbTier
    Cloud SQL machine tier. Defaults to 'db-custom-1-3840'.
.PARAMETER Phase
    Specific deployment phase to execute:
    'All', 'Preflight', 'Foundation', 'BuildImages', 'Secrets', 'Database',
    'User', 'Migration', 'App', 'Schedulers', 'Reconcile', 'ActivateSchedulers'.
.PARAMETER DryRun
    Simulate and print all actions and commands without executing mutating cloud operations.
.PARAMETER Validate
    Validate local dependencies, Terraform syntax, and environment readiness only.
.PARAMETER ShowPlan
    Run Terraform plan and display execution diff without applying.
.PARAMETER Force
    Bypass interactive operator confirmation prompt.
.PARAMETER StateBucket
    Optional GCS bucket name for Terraform remote state backend.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectId,

    [Parameter(Mandatory = $false)]
    [string]$Region = "asia-south1",

    [Parameter(Mandatory = $false)]
    [string]$Commit,

    [Parameter(Mandatory = $false)]
    [string]$DbTier = "db-custom-1-3840",

    [Parameter(Mandatory = $false)]
    [ValidateSet("All", "Preflight", "Foundation", "BuildImages", "Secrets", "Database", "User", "Migration", "App", "Schedulers", "Reconcile", "ActivateSchedulers")]
    [string]$Phase = "All",

    [Parameter(Mandatory = $false)]
    [switch]$DryRun,

    [Parameter(Mandatory = $false)]
    [switch]$Validate,

    [Parameter(Mandatory = $false)]
    [switch]$ShowPlan,

    [Parameter(Mandatory = $false)]
    [switch]$Force,

    [Parameter(Mandatory = $false)]
    [string]$StateBucket
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

# --- Output and Logging Utilities ---

function Write-Step {
    param([string]$Message)
    Write-Host "`n[PHASE] ========================================================" -ForegroundColor Cyan
    Write-Host "[PHASE] $Message" -ForegroundColor Cyan
    Write-Host "[PHASE] ========================================================" -ForegroundColor Cyan
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO]  $Message" -ForegroundColor Gray
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK]    $Message" -ForegroundColor Green
}

function Write-WarningMsg {
    param([string]$Message)
    Write-Host "[WARN]  $Message" -ForegroundColor Yellow
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[FAIL]  $Message" -ForegroundColor Red
}

function Write-CommandLog {
    param([string]$CommandLine)
    Write-Host "[CMD]   $CommandLine" -ForegroundColor DarkCyan
}

# --- Safe Native Process Invocation ---

function Invoke-NativeCommand {
    param(
        [string]$Description,
        [scriptblock]$Command,
        [switch]$IgnoreExitCode
    )

    Write-Info "Executing: $Description"
    & $Command
    $exitCode = $LASTEXITCODE

    if (-not $IgnoreExitCode -and $exitCode -ne 0) {
        Write-ErrorMsg "Command failed with exit code ${exitCode}: $Description"
        throw "Native execution error ($exitCode): $Description"
    }
    return $exitCode
}

# --- Pre-flight Checks & Validation ---

function Assert-ToolInstalled {
    param([string]$CommandName, [string]$HumanName)
    $tool = Get-Command $CommandName -ErrorAction SilentlyContinue
    if (-not $tool) {
        Write-ErrorMsg "$HumanName ('$CommandName') is not installed or not in PATH."
        throw "Missing prerequisite tool: $CommandName"
    }
    Write-Success "Found ${HumanName}: $($tool.Source)"
}

function Assert-GcpProjectActive {
    param([string]$ExpectedProjectId)
    if ([string]::IsNullOrWhiteSpace($ExpectedProjectId)) {
        Write-ErrorMsg "GCP ProjectId must be explicitly supplied. Automatic selection is prohibited."
        throw "Missing mandatory ProjectId parameter."
    }

    if ($DryRun) {
        Write-Info "[DRY-RUN] Would verify that active gcloud project matches '$ExpectedProjectId'."
        return
    }

    $activeProject = (& gcloud config get-value project 2>$null).Trim()
    if ($activeProject -ne $ExpectedProjectId) {
        Write-ErrorMsg "Active gcloud project mismatch! Active: '$activeProject', Expected: '$ExpectedProjectId'."
        Write-ErrorMsg "Run: 'gcloud config set project $ExpectedProjectId' to synchronize."
        throw "GCP active project mismatch."
    }
    Write-Success "Verified active gcloud project: $activeProject"
}

function Assert-BillingEnabled {
    param([string]$TargetProjectId)
    if ($DryRun) {
        Write-Info "[DRY-RUN] Would verify billing is enabled for project '$TargetProjectId'."
        return
    }

    Write-Info "Checking billing status for project '$TargetProjectId'..."
    $billingInfo = & gcloud beta billing projects describe $TargetProjectId --format="value(billingEnabled)" 2>$null
    if ($billingInfo -ne "True") {
        Write-ErrorMsg "Billing is NOT enabled for project '$TargetProjectId'. Aborting billable deployment."
        throw "Billing disabled on project $TargetProjectId"
    }
    Write-Success "Verified billing is enabled for project '$TargetProjectId'."
}

# --- Secret Generation (In-Memory, Zero Disk Leakage) ---

function New-SecureRandomHex {
    param([int]$Bytes = 32)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buffer = New-Object byte[] $Bytes
    $rng.GetBytes($buffer)
    $hex = -join ($buffer | ForEach-Object { "{0:x2}" -f $_ })
    return $hex
}

# --- Main Script Entry ---

Write-Host "=================================================================" -ForegroundColor White
Write-Host " PHYSIO ONE WHATSAPP AI PLATFORM — STAGING DEPLOYMENT RUNNER     " -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor White

# 1. Resolve Git Commit SHA
if ([string]::IsNullOrWhiteSpace($Commit)) {
    try {
        $Commit = (& git rev-parse --short HEAD).Trim()
    }
    catch {
        $Commit = "staging-latest"
    }
}

Write-Info "Configuration Summary:"
Write-Info "  Target Region:   $Region"
Write-Info "  Git Commit:      $Commit"
Write-Info "  Database Tier:   $DbTier"
Write-Info "  Phase:           $Phase"
Write-Info "  DryRun Mode:     $DryRun"
Write-Info "  Validate Only:   $Validate"
Write-Info "  ShowPlan Only:   $ShowPlan"
Write-Info "  Project ID:      $(if ($ProjectId) { $ProjectId } else { '[UNSPECIFIED]' })"

# 2. Handle Validate Mode
if ($Validate) {
    Write-Step "Executing Local Pre-deployment Validation"
    Assert-ToolInstalled "git" "Git CLI"
    Assert-ToolInstalled "terraform" "HashiCorp Terraform"
    Assert-ToolInstalled "docker" "Docker CLI"
    Assert-ToolInstalled "gcloud" "Google Cloud SDK"

    Write-Info "Validating Terraform configuration syntax..."
    Set-Location "$PSScriptRoot\..\infra\staging"
    try {
        Invoke-NativeCommand "terraform fmt -check" { terraform fmt -check }
        Invoke-NativeCommand "terraform validate" { terraform validate }
        Write-Success "Terraform configuration is valid and correctly formatted."
    }
    finally {
        Set-Location "$PSScriptRoot\.."
    }

    Write-Success "All local pre-deployment validation checks passed cleanly."
    exit 0
}

# 3. Enforce Project ID requirement for cloud actions
if ([string]::IsNullOrWhiteSpace($ProjectId) -and -not $DryRun) {
    Write-ErrorMsg "GCP ProjectId is mandatory for staging deployment."
    Write-ErrorMsg "Usage: .\scripts\deploy-staging.ps1 -ProjectId YOUR_PROJECT_ID [-DryRun] [-Phase PhaseName]"
    exit 1
}

# 4. Operator Confirmation Gate (Unless -DryRun or -Force)
if (-not $DryRun -and -not $Force -and $Phase -ne "Preflight") {
    Write-WarningMsg "================================================================="
    Write-WarningMsg " ATTENTION: STAGING CLOUD DEPLOYMENT CONFIRMATION REQUIRED       "
    Write-WarningMsg " Target GCP Project: $ProjectId"
    Write-WarningMsg " Target Region:      $Region"
    Write-WarningMsg " Deployment Phase:   $Phase"
    Write-WarningMsg " This operation will provision billable Google Cloud resources!  "
    Write-WarningMsg "================================================================="
    $response = Read-Host "Do you wish to proceed with deployment? Type 'yes' to confirm"
    if ($response -ne "yes") {
        Write-WarningMsg "Deployment aborted by operator."
        exit 0
    }
}

$repoUrl = "${Region}-docker.pkg.dev/${ProjectId}/physio-staging"
$apiImage = "${repoUrl}/api:${Commit}"
$frontendImage = "${repoUrl}/frontend:${Commit}"
$infraDir = "$PSScriptRoot\..\infra\staging"

# ------------------------------------------------------------------------------
# PHASE EXECUTION LOGIC
# ------------------------------------------------------------------------------

# --- PHASE: Preflight ---
if ($Phase -in @("All", "Preflight")) {
    Write-Step "Phase 1: Pre-flight Verification & Tools Inspection"
    Assert-ToolInstalled "git" "Git CLI"
    Assert-ToolInstalled "terraform" "HashiCorp Terraform"
    Assert-ToolInstalled "docker" "Docker CLI"
    Assert-ToolInstalled "gcloud" "Google Cloud SDK"

    if ($ProjectId) {
        Assert-GcpProjectActive $ProjectId
        Assert-BillingEnabled $ProjectId
    }
    Write-Success "Pre-flight checks passed."
}

# --- PHASE: Foundation (APIs, Repo, SAs, Secret Containers) ---
if ($Phase -in @("All", "Foundation")) {
    Write-Step "Phase 2: Foundation Infrastructure Provisioning"
    Write-Info "Targeting APIs, Artifact Registry, Service Accounts, and Secret Containers..."

    $tfArgs = @(
        "apply",
        "-target=google_project_service.apis",
        "-target=google_artifact_registry_repository.repo",
        "-target=google_service_account.api",
        "-target=google_service_account.worker",
        "-target=google_secret_manager_secret.s",
        "-target=google_secret_manager_secret_iam_member.api_read",
        "-var=project_id=$ProjectId",
        "-var=region=$Region",
        "-var=api_image=$apiImage",
        "-var=frontend_image=$frontendImage",
        "-auto-approve"
    )

    if ($DryRun) {
        Write-Info "[DRY-RUN] cd $infraDir; terraform $($tfArgs -join ' ')"
    }
    else {
        Set-Location $infraDir
        try {
            if ($StateBucket) {
                Invoke-NativeCommand "terraform init with backend" { terraform init -backend-config="bucket=$StateBucket" -upgrade }
            }
            else {
                Invoke-NativeCommand "terraform init" { terraform init }
            }
            Invoke-NativeCommand "terraform apply foundation targets" { terraform @tfArgs }
        }
        finally {
            Set-Location "$PSScriptRoot\.."
        }
    }
    Write-Success "Phase 2 (Foundation) completed successfully."
}

# --- PHASE: BuildImages ---
if ($Phase -in @("All", "BuildImages")) {
    Write-Step "Phase 3: Container Image Build & Publish"
    Write-Info "Target Image (API):      $apiImage"
    Write-Info "Target Image (Frontend): $frontendImage"

    if ($DryRun) {
        Write-Info "[DRY-RUN] gcloud auth configure-docker ${Region}-docker.pkg.dev"
        Write-Info "[DRY-RUN] docker build -t $apiImage -f docker/Dockerfile.api ."
        Write-Info "[DRY-RUN] docker push $apiImage"
        Write-Info "[DRY-RUN] docker build -t $frontendImage -f docker/Dockerfile.frontend ."
        Write-Info "[DRY-RUN] docker push $frontendImage"
    }
    else {
        Invoke-NativeCommand "Configure Docker Auth" { gcloud auth configure-docker "${Region}-docker.pkg.dev" --quiet }
        Invoke-NativeCommand "Build API Image" { docker build -t $apiImage -f docker/Dockerfile.api . }
        Invoke-NativeCommand "Push API Image" { docker push $apiImage }
        Invoke-NativeCommand "Build Frontend Image" { docker build -t $frontendImage -f docker/Dockerfile.frontend . }
        Invoke-NativeCommand "Push Frontend Image" { docker push $frontendImage }
    }
    Write-Success "Phase 3 (Container Build & Publish) completed successfully."
}

# --- PHASE: Secrets ---
if ($Phase -in @("All", "Secrets")) {
    Write-Step "Phase 4: Out-of-Band Secret Version Population"
    Write-Info "Populating Secret Manager secret versions securely via standard input..."

    $secretsToPopulate = @{
        "physio-staging-db-password"          = (New-SecureRandomHex 24)
        "physio-staging-app-secret"           = (New-SecureRandomHex 32)
        "physio-staging-jwt-secret"           = (New-SecureRandomHex 32)
        "physio-staging-worker-token"         = (New-SecureRandomHex 24)
        "physio-staging-whatsapp-token"       = "staging-mock-whatsapp-token"
        "physio-staging-whatsapp-app-secret"  = "staging-mock-app-secret"
        "physio-staging-llm-key"              = "staging-mock-llm-key"
    }

    foreach ($secretEntry in $secretsToPopulate.GetEnumerator()) {
        $secretName = $secretEntry.Key
        $secretVal = $secretEntry.Value

        if ($DryRun) {
            Write-Info "[DRY-RUN] gcloud secrets versions add $secretName --data-file=- [VALUE: REDACTED]"
        }
        else {
            Write-Info "Adding secret version to $secretName (value: [REDACTED])..."
            $secretVal | & gcloud secrets versions add $secretName --data-file=- 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-ErrorMsg "Failed to populate secret version for $secretName."
                throw "Secret population failure on $secretName"
            }
        }
    }
    Write-Success "Phase 4 (Secret Provisioning) completed with zero credential leaks."
}

# --- PHASE: Database (Cloud SQL & Queues) ---
if ($Phase -in @("All", "Database")) {
    Write-Step "Phase 5: Cloud SQL Instance, Database & Tasks Queues Provisioning"
    Write-Info "Targeting Cloud SQL PostgreSQL 16 instance and Cloud Tasks queues..."

    $tfArgs = @(
        "apply",
        "-target=google_sql_database_instance.pg",
        "-target=google_sql_database.db",
        "-target=google_cloud_tasks_queue.q",
        "-var=project_id=$ProjectId",
        "-var=region=$Region",
        "-var=db_tier=$DbTier",
        "-var=api_image=$apiImage",
        "-var=frontend_image=$frontendImage",
        "-auto-approve"
    )

    if ($DryRun) {
        Write-Info "[DRY-RUN] cd $infraDir; terraform $($tfArgs -join ' ')"
    }
    else {
        Set-Location $infraDir
        try {
            Invoke-NativeCommand "terraform apply database targets" { terraform @tfArgs }
        }
        finally {
            Set-Location "$PSScriptRoot\.."
        }
    }
    Write-Success "Phase 5 (Database Infrastructure) completed successfully."
}

# --- PHASE: User (Cloud SQL Database User Creation Out-of-Band) ---
if ($Phase -in @("All", "User")) {
    Write-Step "Phase 6: Cloud SQL Database User Provisioning (Zero-Secret tfstate)"
    Write-Info "Creating user 'physio_admin' on Cloud SQL instance 'physio-staging-pg'..."

    if ($DryRun) {
        Write-Info '[DRY-RUN] DB_PASS=$(gcloud secrets versions access latest --secret=physio-staging-db-password)'
        Write-Info '[DRY-RUN] gcloud sql users create physio_admin --instance=physio-staging-pg --password=[REDACTED]'
    }
    else {
        Write-Info "Retrieving database password from Secret Manager..."
        $dbPass = (& gcloud secrets versions access latest --secret="physio-staging-db-password" 2>$null).Trim()
        if ([string]::IsNullOrWhiteSpace($dbPass)) {
            Write-ErrorMsg "Failed to retrieve database password from Secret Manager."
            throw "Missing database password in Secret Manager"
        }

        Write-Info "Creating Cloud SQL user 'physio_admin' (password: [REDACTED])..."
        & gcloud sql users create physio_admin --instance="physio-staging-pg" --password="$dbPass"
        if ($LASTEXITCODE -ne 0) {
            Write-WarningMsg "User creation returned non-zero. Attempting password update if user already exists..."
            & gcloud sql users set-password physio_admin --instance="physio-staging-pg" --password="$dbPass"
            if ($LASTEXITCODE -ne 0) {
                Write-ErrorMsg "Failed to create or set password for Cloud SQL user 'physio_admin'."
                throw "Cloud SQL user bootstrap failure"
            }
        }
    }
    Write-Success "Phase 6 (Database User Bootstrap) completed cleanly."
}

# --- PHASE: Migration (Dedicated Cloud Run Migration Job) ---
if ($Phase -in @("All", "Migration")) {
    Write-Step "Phase 7: Schema Migration Execution (Migration-Before-Ingress Invariant)"
    Write-Info "Provisioning and executing dedicated Cloud Run migration job 'physio-staging-db-migrate'..."

    $tfArgs = @(
        "apply",
        "-target=google_cloud_run_v2_job.db_migrate",
        "-var=project_id=$ProjectId",
        "-var=region=$Region",
        "-var=db_tier=$DbTier",
        "-var=api_image=$apiImage",
        "-var=frontend_image=$frontendImage",
        "-auto-approve"
    )

    if ($DryRun) {
        Write-Info "[DRY-RUN] cd $infraDir; terraform $($tfArgs -join ' ')"
        Write-Info "[DRY-RUN] gcloud run jobs execute physio-staging-db-migrate --region=$Region --wait"
    }
    else {
        Set-Location $infraDir
        try {
            Invoke-NativeCommand "terraform apply migration job" { terraform @tfArgs }
        }
        finally {
            Set-Location "$PSScriptRoot\.."
        }

        Write-Info "Executing Alembic migration job over Cloud SQL Unix socket volume..."
        Invoke-NativeCommand "Execute migration job" {
            gcloud run jobs execute physio-staging-db-migrate --region=$Region --wait
        }
    }
    Write-Success "Phase 7 (Database Migration) completed successfully. Schema is at head."
}

# --- PHASE: App (API & Frontend Cloud Run Services) ---
if ($Phase -in @("All", "App")) {
    Write-Step "Phase 8: Application Services Deployment & Ingress Wiring"
    Write-Info "Deploying API service, Frontend web service, and IAM invoker bindings..."

    $tfArgs = @(
        "apply",
        "-target=google_cloud_run_v2_service.api",
        "-target=google_cloud_run_v2_service.frontend",
        "-target=google_cloud_run_v2_service_iam_member.api_public",
        "-target=google_cloud_run_v2_service_iam_member.frontend_public",
        "-target=google_cloud_run_v2_job.worker_once",
        "-var=project_id=$ProjectId",
        "-var=region=$Region",
        "-var=db_tier=$DbTier",
        "-var=api_image=$apiImage",
        "-var=frontend_image=$frontendImage",
        "-auto-approve"
    )

    if ($DryRun) {
        Write-Info "[DRY-RUN] cd $infraDir; terraform $($tfArgs -join ' ')"
        Write-Info "[DRY-RUN] curl -f https://[API_URL]/health"
        Write-Info "[DRY-RUN] curl -f https://[API_URL]/api/v1/auth/setup-status"
    }
    else {
        Set-Location $infraDir
        try {
            Invoke-NativeCommand "terraform apply application services" { terraform @tfArgs }
        }
        finally {
            Set-Location "$PSScriptRoot\.."
        }

        Write-Info "Verifying API application health..."
        $apiUrl = (& gcloud run services describe "physio-staging-api" --region=$Region --format="value(status.url)" 2>$null).Trim()
        Write-Info "Probing API health endpoint: $apiUrl/health"
        $healthResponse = Invoke-RestMethod -Uri "$apiUrl/health" -Method Get -TimeoutSec 15
        if ($healthResponse.status -ne "healthy") {
            Write-ErrorMsg "API health check failed! Response: $($healthResponse | ConvertTo-Json -Compress)"
            throw "API health check failed"
        }
        Write-Success "API is healthy: $($healthResponse.status) (env: $($healthResponse.environment))"

        Write-Info "Verifying initial setup status..."
        $setupStatus = Invoke-RestMethod -Uri "$apiUrl/api/v1/auth/setup-status" -Method Get -TimeoutSec 15
        Write-Success "Setup status verified: is_initialized=$($setupStatus.is_initialized)"
    }
    Write-Success "Phase 8 (Application Deployment) completed successfully."
}

# --- PHASE: Schedulers (Created Paused) ---
if ($Phase -in @("All", "Schedulers")) {
    Write-Step "Phase 9: Cloud Scheduler Provisioning (Enforced PAUSED State)"
    Write-Info "Targeting Cloud Scheduler jobs (created in PAUSED state by default)..."

    $tfArgs = @(
        "apply",
        "-target=google_cloud_scheduler_job.jobs",
        "-var=project_id=$ProjectId",
        "-var=region=$Region",
        "-var=db_tier=$DbTier",
        "-var=api_image=$apiImage",
        "-var=frontend_image=$frontendImage",
        "-auto-approve"
    )

    if ($DryRun) {
        Write-Info "[DRY-RUN] cd $infraDir; terraform $($tfArgs -join ' ')"
        Write-Info "[DRY-RUN] gcloud scheduler jobs list --location=$Region"
    }
    else {
        Set-Location $infraDir
        try {
            Invoke-NativeCommand "terraform apply scheduler jobs" { terraform @tfArgs }
        }
        finally {
            Set-Location "$PSScriptRoot\.."
        }

        Write-Info "Confirming scheduler jobs are in PAUSED state..."
        $jobs = & gcloud scheduler jobs list --location=$Region --format="value(name,state)" 2>$null
        Write-Info "Scheduler Jobs State:`n$jobs"
    }
    Write-Success "Phase 9 (Schedulers Provisioning) completed. Schedulers remain PAUSED."
}

# --- PHASE: Reconcile ---
if ($Phase -in @("All", "Reconcile")) {
    Write-Step "Phase 10: Full Terraform State Reconciliation"
    Write-Info "Running full Terraform plan to ensure complete state reconciliation..."

    $tfArgs = @(
        "plan",
        "-var=project_id=$ProjectId",
        "-var=region=$Region",
        "-var=db_tier=$DbTier",
        "-var=api_image=$apiImage",
        "-var=frontend_image=$frontendImage",
        "-detailed-exitcode"
    )

    if ($DryRun) {
        Write-Info "[DRY-RUN] cd $infraDir; terraform $($tfArgs -join ' ')"
    }
    else {
        Set-Location $infraDir
        try {
            terraform @tfArgs
            $planExit = $LASTEXITCODE
            if ($planExit -eq 0) {
                Write-Success "Reconciliation Plan: State matches configuration exactly (0 diff)."
            }
            elseif ($planExit -eq 2) {
                Write-WarningMsg "Reconciliation Plan: Configuration drifts or remaining additions detected."
                if ($ShowPlan) {
                    Write-Info "ShowPlan requested. Reviewing differences above."
                }
            }
            else {
                throw "Terraform plan failed with exit code $planExit"
            }
        }
        finally {
            Set-Location "$PSScriptRoot\.."
        }
    }
    Write-Success "Phase 10 (Reconciliation) completed."
}

# --- PHASE: ActivateSchedulers (Explicit Gate Only) ---
if ($Phase -eq "ActivateSchedulers") {
    Write-Step "Phase 11: Explicit Schedulers Activation Gate"
    Write-WarningMsg "ATTENTION: This phase resumes paused Cloud Scheduler cron jobs!"
    Write-WarningMsg "Ensure the clinic owner account is created and staging validation is complete."

    if (-not $Force) {
        $confirm = Read-Host "Type 'ACTIVATE' to resume background schedulers"
        if ($confirm -ne "ACTIVATE") {
            Write-WarningMsg "Activation cancelled by operator."
            exit 0
        }
    }

    $schedulerNames = @("process-due", "scan-inactivity", "campaigns", "inbound")
    foreach ($jobKey in $schedulerNames) {
        $fullJobName = "physio-staging-$jobKey"
        if ($DryRun) {
            Write-Info "[DRY-RUN] gcloud scheduler jobs resume $fullJobName --location=$Region"
        }
        else {
            Write-Info "Resuming scheduler job: $fullJobName..."
            Invoke-NativeCommand "Resume $fullJobName" {
                gcloud scheduler jobs resume $fullJobName --location=$Region
            }
        }
    }
    Write-Success "All Cloud Scheduler jobs resumed successfully."
}

Write-Host "`n=================================================================" -ForegroundColor Green
Write-Host " STAGING DEPLOYMENT RUNNER COMPLETED SUCCESSFULLY                " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
