param([switch]$Check)

$ErrorActionPreference = 'Stop'
$names = @(
    'DJANGO_DEBUG', 'DJANGO_LOCAL_HTTPS', 'DJANGO_ALLOWED_HOSTS',
    'DJANGO_PRIVATE_CATALOG_ROOT', 'DJANGO_RECEIPTS_KEY_ID',
    'DJANGO_RECEIPTS_PRIVATE_KEY_PATH', 'DJANGO_RECEIPTS_PUBLIC_KEYS_DIR',
    'DJANGO_SECRET_KEY_DPAPI_PATH', 'DJANGO_RECEIPTS_PASSWORD_DPAPI_PATH',
    'DJANGO_SECRET_KEY', 'DJANGO_RECEIPTS_PRIVATE_KEY_PASSWORD',
    'DJANGO_SETTINGS_MODULE'
)
$previous = @{}
foreach ($name in $names) {
    $item = Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    if ($null -ne $item) { $previous[$name] = $item.Value }
}

function Assert-File([string]$Path, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Falta el archivo requerido: $Label."
    }
}

function Read-DpapiSecret([string]$Path) {
    $protected = [IO.File]::ReadAllBytes($Path)
    try {
        $plain = [Security.Cryptography.ProtectedData]::Unprotect(
            $protected, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
    } catch [Security.Cryptography.CryptographicException] {
        throw 'No se pudo descifrar el secreto DPAPI con el usuario actual de Windows.'
    }
    try {
        $utf8 = New-Object Text.UTF8Encoding($false, $true)
        try {
            $value = $utf8.GetString($plain)
        } catch [Text.DecoderFallbackException] {
            throw 'El secreto DPAPI no contiene texto UTF-8 valido.'
        }
        if ([string]::IsNullOrWhiteSpace($value)) { throw 'El secreto DPAPI esta vacio.' }
        return $value
    } finally {
        [Array]::Clear($plain, 0, $plain.Length)
    }
}

function Assert-PortAvailable {
    $listeners = [Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if ($listeners | Where-Object { $_.Port -eq 8000 }) {
        throw 'El puerto 8000 esta ocupado. No se iniciara otro servidor.'
    }
}

Push-Location $PSScriptRoot
try {
    $python = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
    foreach ($relative in @('venv\Scripts\python.exe', '.env', 'manage.py', 'config\settings.py', 'Caddyfile', 'db.sqlite3')) {
        Assert-File (Join-Path $PSScriptRoot $relative) $relative
    }
    if (-not $Check) { Assert-PortAvailable }

    $loadConfig = @'
import json
import os
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

path = Path.cwd() / '.env'
for name in ('DJANGO_SECRET_KEY', 'DJANGO_RECEIPTS_PRIVATE_KEY_PASSWORD'):
    if name in dotenv_values(path):
        raise SystemExit('No guarde secretos en .env; utilice los archivos DPAPI.')
load_dotenv(path, override=False)
names = (
    'DJANGO_DEBUG', 'DJANGO_LOCAL_HTTPS', 'DJANGO_ALLOWED_HOSTS',
    'DJANGO_PRIVATE_CATALOG_ROOT', 'DJANGO_RECEIPTS_KEY_ID',
    'DJANGO_RECEIPTS_PRIVATE_KEY_PATH', 'DJANGO_RECEIPTS_PUBLIC_KEYS_DIR',
    'DJANGO_SECRET_KEY_DPAPI_PATH', 'DJANGO_RECEIPTS_PASSWORD_DPAPI_PATH',
)
print(json.dumps({name: os.environ.get(name, '') for name in names}))
'@
    $json = & $python -B -c $loadConfig
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo cargar .env con python-dotenv.' }
    $config = $json | ConvertFrom-Json
    foreach ($property in $config.PSObject.Properties) {
        if ([string]::IsNullOrWhiteSpace($property.Value)) {
            throw "Falta la configuracion requerida: $($property.Name)."
        }
        Set-Item -Path "Env:$($property.Name)" -Value $property.Value
    }
    if ($env:DJANGO_DEBUG -ine 'false' -or $env:DJANGO_LOCAL_HTTPS -ine 'true') {
        throw 'El inicio seguro requiere DJANGO_DEBUG=false y DJANGO_LOCAL_HTTPS=true.'
    }
    if ($env:DJANGO_ALLOWED_HOSTS.Trim() -cne 'localhost') {
        throw 'El inicio seguro requiere DJANGO_ALLOWED_HOSTS=localhost.'
    }
    foreach ($name in @(
        'DJANGO_PRIVATE_CATALOG_ROOT', 'DJANGO_RECEIPTS_PRIVATE_KEY_PATH',
        'DJANGO_RECEIPTS_PUBLIC_KEYS_DIR', 'DJANGO_SECRET_KEY_DPAPI_PATH',
        'DJANGO_RECEIPTS_PASSWORD_DPAPI_PATH'
    )) {
        $path = (Get-Item -Path "Env:$name").Value
        if (-not [IO.Path]::IsPathRooted($path)) { throw "$name requiere una ruta absoluta." }
    }
    if (-not (Test-Path -LiteralPath $env:DJANGO_PRIVATE_CATALOG_ROOT -PathType Container)) {
        throw 'No existe el directorio privado del catalogo.'
    }
    Assert-File $env:DJANGO_RECEIPTS_PRIVATE_KEY_PATH 'clave privada RSA'
    if ($env:DJANGO_RECEIPTS_KEY_ID -cnotmatch '^[A-Za-z0-9_-]{1,64}$') {
        throw 'Identificador de clave RSA invalido.'
    }
    Assert-File (Join-Path $env:DJANGO_RECEIPTS_PUBLIC_KEYS_DIR ($env:DJANGO_RECEIPTS_KEY_ID + '.pem')) 'clave publica RSA'
    Assert-File $env:DJANGO_SECRET_KEY_DPAPI_PATH 'DJANGO_SECRET_KEY DPAPI'
    Assert-File $env:DJANGO_RECEIPTS_PASSWORD_DPAPI_PATH 'contrasena RSA DPAPI'
    Add-Type -AssemblyName System.Security
    $env:DJANGO_SECRET_KEY = Read-DpapiSecret $env:DJANGO_SECRET_KEY_DPAPI_PATH
    $env:DJANGO_RECEIPTS_PRIVATE_KEY_PASSWORD = Read-DpapiSecret $env:DJANGO_RECEIPTS_PASSWORD_DPAPI_PATH
    $env:DJANGO_SETTINGS_MODULE = 'config.settings'

    $verifyConfig = @'
from pathlib import Path
import sys
import django
django.setup()
from django.conf import settings
from receipts.crypto import (
    ALGORITHM, FORMAT, InvalidReceipt, ReceiptConfigurationError,
    signing_key, sign_body, verify_envelope,
)

if Path(settings.DATABASES['default']['NAME']).resolve() != Path.cwd() / 'db.sqlite3':
    raise SystemExit('La base configurada no es db.sqlite3 del proyecto activo.')
try:
    key_id, private = signing_key()
    body = {'format': FORMAT, 'algorithm': ALGORITHM, 'key_id': key_id, 'purpose': 'startup-check'}
    digest, signature = sign_body(body, private)
    if verify_envelope({'body': body, 'sha256': digest, 'signature': signature}) != body:
        raise InvalidReceipt('Fallo la comprobacion criptografica.')
except (InvalidReceipt, ReceiptConfigurationError):
    print('Error: no se pudo validar la pareja RSA y su firma; revise las claves y el secreto DPAPI.')
    sys.exit(1)
print('Configuracion y firma RSA verificadas sin crear registros.')
'@
    & $python -B -c $verifyConfig
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la comprobacion de configuracion o claves.' }
    & $python -B manage.py check
    if ($LASTEXITCODE -ne 0) { throw 'Django detecto errores de configuracion.' }
    if (-not $Check) {
        Assert-PortAvailable
        & $python -B manage.py runserver 127.0.0.1:8000 --noreload
        if ($LASTEXITCODE -ne 0) { throw "Django termino con codigo $LASTEXITCODE." }
    }
} finally {
    foreach ($name in $names) {
        if ($previous.ContainsKey($name)) {
            Set-Item -Path "Env:$name" -Value $previous[$name]
        } else {
            Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        }
    }
    Pop-Location
}
