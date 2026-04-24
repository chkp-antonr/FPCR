param(
	[switch]$EnforcePyright,
	[switch]$EnforceMypy,
	[switch]$EnforceTypes
)

function Invoke-Step {
	param(
		[string]$Name,
		[scriptblock]$Action,
		[switch]$Optional
	)

	Write-Host "`n==> $Name"
	& $Action 2>&1 | Out-Host
	$exitCode = $LASTEXITCODE

	if ($exitCode -eq 0) {
		Write-Host "[OK] $Name"
		return $true
	}

	if ($Optional) {
		Write-Warning "[WARN] $Name failed with exit code $exitCode (optional)."
		return $true
	}

	Write-Host "[FAIL] $Name failed with exit code $exitCode." -ForegroundColor Red
	return $false
}

$allPassed = $true

if (-not (Invoke-Step -Name "Ruff check --fix" -Action { uv run ruff check --fix src/ })) {
	$allPassed = $false
}
if (-not (Invoke-Step -Name "Ruff format" -Action { uv run ruff format src/ })) {
	$allPassed = $false
}

if ($EnforceTypes -or $EnforcePyright) {
	if (-not (Invoke-Step -Name "Pyright (enforced)" -Action { uv run pyright src/ })) {
		$allPassed = $false
	}
}
else {
	if (-not (Invoke-Step -Name "Pyright (informational)" -Action { uv run pyright src/ } -Optional)) {
		$allPassed = $false
	}
}

if ($EnforceTypes -or $EnforceMypy) {
	if (-not (Invoke-Step -Name "Mypy (enforced)" -Action { uv run mypy src/ })) {
		$allPassed = $false
	}
}
else {
	if (-not (Invoke-Step -Name "Mypy (informational)" -Action { uv run mypy src/ } -Optional)) {
		$allPassed = $false
	}
}

if ($allPassed) {
	Write-Host "`nAll checks completed."
	exit 0
}

exit 1
