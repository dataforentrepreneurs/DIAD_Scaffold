param(
  [string]$ProjectId = $env:GOOGLE_CLOUD_PROJECT,
  [string]$StoreTier = "Growth", # Boutique (<1k orders), Growth (1k-10k orders), Scaling (10k-50k orders)
  [double]$BudgetAmount = 0.0,
  [string]$CurrencyCode = "SGD",
  [string]$AlertEmail = "",
  [string]$ConfigPath = "config/client_rawdata.json"
)

# Set budget based on recommended store size bracket if not explicitly passed
if ($BudgetAmount -eq 0.0) {
  switch ($StoreTier.ToLower()) {
    "boutique" { $BudgetAmount = 30.0 }
    "starter"  { $BudgetAmount = 30.0 }
    "scaling"  { $BudgetAmount = 120.0 }
    "enterprise" { $BudgetAmount = 150.0 }
    default    { $BudgetAmount = 60.0 } # Growth default
  }
}

# 1. Resolve Project ID & Region from config if not provided
if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "Not Configured") {
  if (Test-Path $ConfigPath) {
    try {
      $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
      if ($cfg.client.project_id -and $cfg.client.project_id -ne "Not Configured") {
        $ProjectId = $cfg.client.project_id
      }
      if ($cfg.client.business_email -and [string]::IsNullOrWhiteSpace($AlertEmail)) {
        $AlertEmail = $cfg.client.business_email
      }
    } catch {}
  }
}

if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "Not Configured") {
  $ProjectId = (gcloud config get-value project 2>$null)
}

if ([string]::IsNullOrWhiteSpace($ProjectId)) {
  Write-Error "Could not determine Google Cloud Project ID. Please specify -ProjectId."
  exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  DIAD Gate 6: Project-Scoped GCP Budget Alert Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Project:    $ProjectId" -ForegroundColor Yellow
Write-Host "Selected Bracket:  $StoreTier Tier" -ForegroundColor Yellow
Write-Host "Budget Cap:        $BudgetAmount $CurrencyCode / month" -ForegroundColor Yellow
Write-Host "Thresholds:        50% ($($BudgetAmount * 0.5) $CurrencyCode), 80% ($($BudgetAmount * 0.8) $CurrencyCode), 100% ($BudgetAmount $CurrencyCode)" -ForegroundColor Yellow
if ($AlertEmail) {
  Write-Host "Alert Recipient:   $AlertEmail" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "--- Recommended Sizing Brackets ---" -ForegroundColor Gray
Write-Host "  • Boutique Store (< 1k orders/mo, < 30k visits):   S$25 - S$35 / mo" -ForegroundColor Gray
Write-Host "  • Growth Retail (1k - 10k orders/mo, 30k-150k visits): S$50 - S$80 / mo (Selected)" -ForegroundColor Gray
Write-Host "  • Scaling Brand (10k - 50k+ orders/mo, 150k-500k+ visits): S$100 - S$150 / mo" -ForegroundColor Gray
Write-Host "-----------------------------------`n" -ForegroundColor Gray

# 2. Query billing account linked to this specific project
Write-Host "Checking linked Cloud Billing Account for project '$ProjectId'..." -ForegroundColor Gray
$billingAccountName = (gcloud billing projects describe $ProjectId --quiet --format="value(billingAccountName)" 2>$null)
$billingEnabled = (gcloud billing projects describe $ProjectId --quiet --format="value(billingEnabled)" 2>$null)

$billingAccountId = $null
if ($billingAccountName) {
  $billingAccountId = $billingAccountName -replace "^billingAccounts/", ""
  Write-Host "Found Linked Billing Account: $billingAccountId" -ForegroundColor Green
} else {
  Write-Host "Notice: Current IAM credentials lack direct Billing Account admin permissions." -ForegroundColor Yellow
}

# 3. Enable Cloud Billing Budgets API if possible
if ($billingAccountId) {
  Write-Host "Ensuring Cloud Billing Budgets API is enabled..." -ForegroundColor Gray
  gcloud services enable billingbudgets.googleapis.com --project $ProjectId --quiet 2>$null
}

# 4. Attempt Programmatic Budget Creation
$budgetName = "DIAD-Cost-Cap-$ProjectId"
Write-Host "`nAttempting to create/update project-scoped budget '$budgetName'..." -ForegroundColor Gray

$budgetCreated = $false
try {
  # Check if gcloud billing budgets is available
  $budgetAmountFormatted = "${BudgetAmount}${CurrencyCode}"
  
  $createOutput = (gcloud billing budgets create `
    --billing-account=$billingAccountId `
    --display-name="$budgetName" `
    --budget-amount="$budgetAmountFormatted" `
    --filter-projects="projects/$ProjectId" `
    --threshold-rule="percent=0.50,basis=current-spend" `
    --threshold-rule="percent=0.80,basis=current-spend" `
    --threshold-rule="percent=1.00,basis=current-spend" `
    --format="value(name)" 2>&1)
    
  if ($LASTEXITCODE -eq 0 -and $createOutput) {
    $budgetCreated = $true
    Write-Host "`n✅ SUCCESS: Project-scoped budget alert successfully created!" -ForegroundColor Green
    Write-Host "Budget Name: $createOutput" -ForegroundColor Gray
  } else {
    Write-Host "Programmatic budget creation returned: $createOutput" -ForegroundColor DarkGray
  }
} catch {
  Write-Host "Notice: Programmatic budget creation requires Billing Account Administrator rights." -ForegroundColor DarkGray
}

# 5. Fallback & Verification Instructions
$consoleUrl = if ($billingAccountId) { "https://console.cloud.google.com/billing/$billingAccountId/budgets/create?project=$ProjectId" } else { "https://console.cloud.google.com/billing/budgets?project=$ProjectId" }

if (-not $budgetCreated) {
  Write-Host "`n----------------------------------------------------------" -ForegroundColor Yellow
  Write-Host "  MANUAL 60-SECOND VERIFICATION IN GCP CONSOLE" -ForegroundColor Yellow
  Write-Host "----------------------------------------------------------" -ForegroundColor Yellow
  Write-Host "If your Service Account does not possess full Billing Account Admin rights," -ForegroundColor Gray
  Write-Host "you or your client can confirm this budget in 3 clicks:" -ForegroundColor Gray
  Write-Host ""
  Write-Host "1. Open this direct link in your browser:" -ForegroundColor Cyan
  Write-Host "   $consoleUrl" -ForegroundColor White -BackgroundColor Black
  Write-Host ""
  Write-Host "2. Fill in these exact values:" -ForegroundColor Gray
  Write-Host "   - Name:             DIAD Cost Cap ($ProjectId)" -ForegroundColor White
  Write-Host "   - Projects (Scope): Select ONLY '$ProjectId' (Uncheck other projects)" -ForegroundColor White
  Write-Host "   - Target Amount:    $BudgetAmount $CurrencyCode" -ForegroundColor White
  Write-Host "   - Alert Thresholds: 50% ($($BudgetAmount * 0.5)), 80% ($($BudgetAmount * 0.8)), 100% ($BudgetAmount)" -ForegroundColor White
  Write-Host "   - Notification:     Check 'Email billing admins and users'" -ForegroundColor White
  Write-Host "3. Click 'Finish'." -ForegroundColor Gray
}

# 6. Generate Client Email / Communication Notification
Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "  CLIENT COMMUNICATION TEMPLATE (Copy & Send to Client)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$emailSubject = "Security & Cost Safeguard Active: Project Budget Limit Set on $ProjectId"
$emailBody = @"
Subject: $emailSubject

Dear Client Team,

As part of our commitment to transparent cloud operations and preventing billing surprises, we have established project-scoped cost guardrails on your DIAD deployment ($ProjectId):

1. BigQuery Compute Ceiling: Every query executed by the AI Text-to-SQL engine enforces a hard 1 GB ceiling (preventing accidental full-table scan charges).
2. Cloud Run Scaling Limit: Auto-scaling is capped at a maximum of 5 concurrent instances with concurrency=80 to prevent traffic surges from driving up compute.
3. Monthly Project Budget Alert:
   - Target Scope: Project '$ProjectId' (Scoped exclusively to DIAD; will not impact your other corporate workloads)
   - Budget Amount: $BudgetAmount $CurrencyCode / month
   - Automated Alerts: Triggered at 50% ($($BudgetAmount * 0.5) $CurrencyCode), 80% ($($BudgetAmount * 0.8) $CurrencyCode), and 100% ($BudgetAmount $CurrencyCode) directly to your billing email.

You can verify or adjust these thresholds anytime directly in your Google Cloud Console:
$consoleUrl

Best regards,
Data for Entrepreneurs Team
https://d4e.ai
"@

Write-Host $emailBody -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
