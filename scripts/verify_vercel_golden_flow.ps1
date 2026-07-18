param(
    [Parameter(Mandatory = $true)]
    [string]$Deployment,
    [string]$Output = "reports/vercel-golden-flow.json",
    [ValidateRange(1, 2)]
    [int]$Iterations = 2,
    [switch]$ProductionSafe
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("crowdcue-vercel-" + [guid]::NewGuid())
$null = New-Item -ItemType Directory -Path $temporaryRoot
$env:npm_config_cache = Join-Path $repositoryRoot ".npm-cache"

function Assert-Condition([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Invoke-CrowdCueApi {
    param(
        [string]$Method,
        [string]$Path,
        [int]$ExpectedStatus,
        [string]$SessionId = "",
        [object]$Body = $null
    )

    $requestId = [guid]::NewGuid().ToString()
    $headersPath = Join-Path $temporaryRoot "$requestId.headers"
    $responsePath = Join-Path $temporaryRoot "$requestId.json"
    $arguments = @(
        "vercel", "curl", $Path, "--deployment", $Deployment, "--",
        "--silent", "--show-error", "--dump-header", $headersPath,
        "--output", $responsePath, "--request", $Method
    )
    if ($SessionId) {
        $arguments += @("--header", "X-Session-ID: $SessionId")
    }
    if ($null -ne $Body) {
        $requestPath = Join-Path $temporaryRoot "$requestId.request.json"
        $Body | ConvertTo-Json -Depth 20 -Compress | Set-Content -Encoding utf8 $requestPath
        $arguments += @(
            "--header", "Content-Type: application/json",
            "--data-binary", "@$requestPath"
        )
    }

    $null = & npx @arguments
    if ($LASTEXITCODE -ne 0) { throw "Vercel request failed: $Method $Path" }
    $statusLine = Get-Content $headersPath | Select-String '^HTTP/' | Select-Object -Last 1
    if ($null -eq $statusLine) { throw "Missing HTTP status: $Method $Path" }
    $statusCode = [int](($statusLine.Line -split ' ')[1])
    if ($statusCode -ne $ExpectedStatus) {
        $safeBody = (Get-Content $responsePath -Raw).Substring(
            0, [Math]::Min(1000, (Get-Item $responsePath).Length)
        )
        throw "$Method $Path returned $statusCode, expected $ExpectedStatus`: $safeBody"
    }
    $payload = Get-Content $responsePath -Raw | ConvertFrom-Json
    return [pscustomobject]@{ Status = $statusCode; Payload = $payload }
}

function Invoke-GoldenFlowIteration([int]$Iteration) {
    $sessionId = [guid]::NewGuid().ToString()
    $created = (Invoke-CrowdCueApi POST "/api/runs" 201 "" @{
        session_id = $sessionId
        scenario_key = "gate_convergence"
    }).Payload
    $runId = $created.run_id
    $candidate = $created.candidates | Where-Object candidate_key -eq "cand-west-gate-a"
    $invalidCandidate = $created.candidates | Where-Object candidate_key -eq "cand-east-gate-c"
    Assert-Condition ($null -ne $candidate -and $candidate.is_viable) "Gate A candidate is not viable."
    Assert-Condition ($null -ne $invalidCandidate -and -not $invalidCandidate.is_viable) "Invalid Gate C candidate was not rejected."

    $selected = (Invoke-CrowdCueApi POST "/api/runs/$runId/select-candidate" 200 $sessionId @{
        candidate_id = $candidate.id
    }).Payload
    Assert-Condition ($selected.lifecycle_state -eq "CANDIDATE_SELECTED") "Candidate selection failed."

    if ($ProductionSafe) {
        $null = Invoke-CrowdCueApi POST "/api/runs/$runId/generate-guidance" 422 $sessionId @{
            enable_fault_injection = $true
        }
        $generated = (Invoke-CrowdCueApi POST "/api/runs/$runId/generate-guidance" 200 $sessionId @{
            enable_fault_injection = $false
        }).Payload
        $codes = @($generated.diagnostics | ForEach-Object code)
        Assert-Condition ($generated.lifecycle_state -eq "SEMANTIC_PASSED") "Production-safe guidance did not pass."
        Assert-Condition ($generated.variants.Count -eq 6 -and $codes.Count -eq 0) "Production-safe guidance evidence is incomplete."
        $blockedSpanish = $null
        $repaired = $null
        $unaffectedHashCount = $null
    }
    else {
        $generated = (Invoke-CrowdCueApi POST "/api/runs/$runId/generate-guidance" 200 $sessionId @{
            enable_fault_injection = $true
        }).Payload
        $codes = @($generated.diagnostics | ForEach-Object code)
        Assert-Condition ($generated.lifecycle_state -eq "PREFLIGHT_BLOCKED") "Injected omission was not blocked."
        Assert-Condition ($generated.variants.Count -eq 6) "Expected six guidance variants."
        Assert-Condition ($codes -contains "PROTECTED_COHORT_OMITTED") "Protection omission was not diagnosed."
        $blockedSpanish = $generated.variants | Where-Object { $_.language -eq "es" -and $_.channel -eq "fan_app" }
        Assert-Condition ($blockedSpanish.version -eq 1) "Blocked Spanish version 1 is missing."

        $null = Invoke-CrowdCueApi POST "/api/runs/$runId/approve" 409 $sessionId @{
            approved_by_user_id = [guid]::NewGuid().ToString()
            approver_role = "SUPERVISOR"
            approval_note = "Must remain blocked."
            expected_bundle_hash = "0" * 64
        }

        $repaired = (Invoke-CrowdCueApi POST "/api/runs/$runId/repair" 200 $sessionId).Payload
        Assert-Condition ($repaired.lifecycle_state -eq "SEMANTIC_PASSED") "Repair did not pass semantic verification."
        Assert-Condition ($repaired.repaired_variant.version -eq 2) "Repair did not create immutable version 2."
        $unaffectedHashCount = @($repaired.unaffected_variant_hashes.PSObject.Properties).Count
        Assert-Condition ($unaffectedHashCount -eq 5) "Five unaffected hashes were not preserved."
        Assert-Condition ($repaired.unaffected_spanish_clauses_unchanged) "Repair changed an unaffected Spanish clause."
        Assert-Condition ($repaired.original_variant_id -ne $repaired.repaired_variant_id) "Repair overwrote version 1."
    }

    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    $simulated = (Invoke-CrowdCueApi POST "/api/runs/$runId/simulate" 200 $sessionId).Payload
    $stopwatch.Stop()
    $simulation = $simulated.simulation
    Assert-Condition ($simulation.sample_count -eq 200 -and $simulation.paired) "Simulation was not 200 paired samples."
    Assert-Condition ($simulation.verdict -eq "PASS") "Simulation did not pass."
    Assert-Condition ($simulation.protected_route_violations -eq 0) "Protected route invariant failed."

    $details = (Invoke-CrowdCueApi GET "/api/runs/$runId" 200 $sessionId).Payload
    $bundleHash = $details.expected_bundle_hash
    Assert-Condition ($bundleHash -match '^[0-9a-f]{64}$') "Server approval bundle hash is missing."
    $null = Invoke-CrowdCueApi POST "/api/runs/$runId/approve" 409 $sessionId @{
        approved_by_user_id = [guid]::NewGuid().ToString()
        approver_role = "SUPERVISOR"
        approval_note = "Stale hash check."
        expected_bundle_hash = "f" * 64
    }

    $approved = (Invoke-CrowdCueApi POST "/api/runs/$runId/approve" 201 $sessionId @{
        approved_by_user_id = [guid]::NewGuid().ToString()
        approver_role = "SUPERVISOR"
        approval_note = "Synthetic Golden Flow evidence reviewed."
        expected_bundle_hash = $bundleHash
    }).Payload
    Assert-Condition ($approved.lifecycle_state -eq "APPROVED") "Approval failed."

    $published = (Invoke-CrowdCueApi POST "/api/runs/$runId/publish" 202 $sessionId).Payload
    Assert-Condition ($published.lifecycle_state -eq "PUBLISHED" -and $published.simulated) "Simulated publication failed."
    Assert-Condition ($published.deliveries.Count -eq 10) "Expected ten simulated deliveries."

    $final = (Invoke-CrowdCueApi GET "/api/runs/$runId" 200 $sessionId).Payload
    $refresh = (Invoke-CrowdCueApi GET "/api/runs/$runId" 200 $sessionId).Payload
    Assert-Condition ($final.lifecycle_state -eq "PUBLISHED" -and $refresh.lifecycle_state -eq "PUBLISHED") "Refresh did not restore PUBLISHED."
    Assert-Condition ($final.run_id -eq $refresh.run_id -and $final.publication_deliveries.Count -eq 10) "Refresh changed persisted evidence."
    Assert-Condition ($final.approval.bundle_hash -eq $bundleHash) "Persisted approval hash changed."

    $audit = (Invoke-CrowdCueApi GET "/api/runs/$runId/audit" 200 $sessionId).Payload
    $eventTypes = @($audit.events | ForEach-Object event_type)
    Assert-Condition ($audit.chain_valid) "Audit chain is invalid."
    $requiredEvents = if ($ProductionSafe) {
        @("SEMANTIC_PASSED", "SIMULATION_COMPLETED", "APPROVAL_RECORDED", "PUBLICATION_COMPLETED")
    } else {
        @("DEMO_FAULT_INJECTED", "SEMANTIC_BLOCKED", "TARGETED_REPAIR_COMPLETED", "SIMULATION_COMPLETED", "APPROVAL_RECORDED", "PUBLICATION_COMPLETED")
    }
    foreach ($requiredEvent in $requiredEvents) {
        Assert-Condition ($eventTypes -contains $requiredEvent) "Missing audit event $requiredEvent."
    }
    if ($ProductionSafe) {
        Assert-Condition ($eventTypes -notcontains "DEMO_FAULT_INJECTED") "Production recorded a demo fault."
    }

    return [ordered]@{
        iteration = $Iteration
        run_id = $runId
        session_id = $sessionId
        final_state = $final.lifecycle_state
        selected_candidate = $candidate.candidate_key
        rejected_candidate = $invalidCandidate.candidate_key
        blocked_diagnostic_codes = $codes
        production_safe = [bool]$ProductionSafe
        fault_injection_rejection_status = if ($ProductionSafe) { 422 } else { $null }
        blocked_spanish_version = if ($blockedSpanish) { $blockedSpanish.version } else { $null }
        repaired_spanish_version = if ($repaired) { $repaired.repaired_variant.version } else { $null }
        original_variant_id = if ($repaired) { $repaired.original_variant_id } else { $null }
        repaired_variant_id = if ($repaired) { $repaired.repaired_variant_id } else { $null }
        unaffected_variant_hash_count = $unaffectedHashCount
        unaffected_spanish_clauses_unchanged = if ($repaired) { $repaired.unaffected_spanish_clauses_unchanged } else { $null }
        generation_provenance = $final.generation_provenance
        simulation = $simulation
        simulation_duration_ms = $stopwatch.ElapsedMilliseconds
        approval_bundle_hash = $bundleHash
        stale_approval_status = 409
        blocked_approval_status = if ($ProductionSafe) { $null } else { 409 }
        publication_simulated = $published.simulated
        publication_delivery_count = $final.publication_deliveries.Count
        publication_surfaces = @($final.publication_deliveries | ForEach-Object surface | Sort-Object -Unique)
        audit_chain_valid = $audit.chain_valid
        audit_event_types = $eventTypes
        refresh_restored = $true
    }
}

try {
    $runs = @()
    for ($iteration = 1; $iteration -le $Iterations; $iteration++) {
        $runs += Invoke-GoldenFlowIteration $iteration
    }
    $reproducible = $Iterations -eq 1 -or (
        $runs[0].simulation.result_hash -eq $runs[1].simulation.result_hash -and
        $runs[0].simulation.samples_hash -eq $runs[1].simulation.samples_hash
    )
    Assert-Condition $reproducible "Fixed-seed paired simulation was not reproducible."
    $result = [ordered]@{
        verified = $true
        deployment = $Deployment
        mode = if ($ProductionSafe) { "production-safe" } else { "protected-demo" }
        iterations = $Iterations
        fixed_seed_reproducible = $reproducible
        runs = $runs
        verified_at_utc = [DateTime]::UtcNow.ToString("o")
    }
    $outputPath = if ([IO.Path]::IsPathRooted($Output)) { $Output } else { Join-Path $repositoryRoot $Output }
    $null = New-Item -ItemType Directory -Force -Path (Split-Path $outputPath)
    $result | ConvertTo-Json -Depth 30 | Set-Content -Encoding utf8 $outputPath
    $result | ConvertTo-Json -Depth 30
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
