param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedManifestSha256,
    [ValidatePattern('^[A-Za-z0-9_-]{1,64}$')][string]$Name,
    [switch]$AllowKnownGaps
)

$ErrorActionPreference = 'Stop'
$python = Join-Path (Split-Path $PSScriptRoot -Parent) 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'No existe el interprete confiable del proyecto.'
}
$arguments = @(
    '-B', (Join-Path $PSScriptRoot 'recovery.py'), 'restore',
    '--backup-path', $BackupPath, '--expected-manifest-sha256', $ExpectedManifestSha256
)
if ($Name) { $arguments += @('--name', $Name) }
if ($AllowKnownGaps) { $arguments += '--allow-known-gaps' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'La restauracion fue rechazada o fallo; no utilice carpetas .partial.' }
