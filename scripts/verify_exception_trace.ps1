# Read-only verification; credentials stay in this process environment, never arguments/output.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$localEvidence = Join-Path $root '.local/exception-preflight'
$result = Get-Content -LiteralPath (Join-Path $localEvidence 'result.json') -Raw | ConvertFrom-Json
$previous = @{}
try {
    foreach ($line in Get-Content -LiteralPath (Join-Path $root 'backend/.env')) {
        if ($line -match '^\s*(LANGFUSE_(?:PUBLIC_KEY|SECRET_KEY|HOST|BASE_URL))\s*=(.*)$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
    if (-not $env:LANGFUSE_BASE_URL) {
        if (-not $previous.ContainsKey('LANGFUSE_BASE_URL')) { $previous['LANGFUSE_BASE_URL'] = $null }
        $env:LANGFUSE_BASE_URL = $env:LANGFUSE_HOST
    }
    $raw = & npx --yes langfuse-cli api observations list --trace-id $result.restricted_record.trace_id --fields core,basic,io,metadata,model,usage --limit 100 --json
    if ($LASTEXITCODE -ne 0) { throw 'Langfuse query failed; no verification recorded' }
    $text = $raw -join "`n"
    foreach ($fake in @('SYNTHETIC_PED_MARIGOLD_84621', 'SYNTHETIC_PED_CEDAR_39217')) {
        if ($text.Contains($fake)) { throw 'Synthetic content found in Langfuse; inspect privately' }
    }
    $parsed = $text | ConvertFrom-Json
    $text | Set-Content -LiteralPath (Join-Path $localEvidence 'langfuse.json') -Encoding utf8
    $observations = @($parsed.body.data)
    $report = @($observations | Where-Object { $_.name -eq 'explanation-report' })
    $rootSpan = @($observations | Where-Object { $_.isRootObservation })
    if ($report.Count -ne 1 -or $report[0].level -ne 'ERROR') { throw 'Missing report error span' }
    if ($report[0].metadata.error_refs -notcontains $result.restricted_record.error_ref) {
        throw 'Error reference is not linked to the report span'
    }
    if ($rootSpan.Count -ne 1 -or $rootSpan[0].metadata.decision_trace_id -ne $result.decision_trace.id) {
        throw 'Decision trace is not linked to the root span'
    }
    $summary = [ordered]@{
        trace_id = $result.restricted_record.trace_id
        observation_count = $observations.Count
        error_node = $report[0].name
        error_level = $report[0].level
        error_ref = $result.restricted_record.error_ref
        decision_trace_id = $rootSpan[0].metadata.decision_trace_id
        fake_values_absent = $true
        sdk_version = $rootSpan[0].metadata.'scope.version'
    }
    $summary | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $localEvidence 'langfuse-summary.json') -Encoding utf8
    $summary | ConvertTo-Json
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process')
    }
}
