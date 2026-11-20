param([switch]$AllowKnownGaps)

$ErrorActionPreference = 'Stop'
$python = Join-Path (Split-Path $PSScriptRoot -Parent) 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'No existe el interprete del entorno virtual del proyecto.'
}
$arguments = @('-B', (Join-Path $PSScriptRoot 'recovery.py'), 'backup')
if ($AllowKnownGaps) { $arguments += '--allow-known-gaps' }
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'El respaldo fallo; no utilice carpetas .partial como respaldos validos.' }
