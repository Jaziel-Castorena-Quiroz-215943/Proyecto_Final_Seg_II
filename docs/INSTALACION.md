# Instalación nueva en Windows

[Índice general](../README.md) · [HTTPS](HTTPS_PKI.md) · [Recuperación](RESPALDO_RESTAURACION.md)

## 1. Condición indispensable

Esta guía inicializa **una instalación nueva y vacía**, con claves propias y
datos nuevos. No es una receta para reparar la carpeta activa ni para recrear
el histórico. **Los comandos no fueron ejecutados durante la documentación.**
Una instalación limpia con descarga de paquetes sigue pendiente de validación.

Si existe SQLite, `.env`, material RSA o secretos previos, detenerse y utilizar
el procedimiento de recuperación autorizado. No ejecutar migraciones,
`createsuperuser` ni generación de secretos sobre el proyecto conservado.
Claves nuevas no verifican firmas antiguas; PDF nuevos no reemplazan versiones
históricas.

## 2. Requisitos

- Windows y Windows PowerShell 5.1, con Python 3.13 y el lanzador `py`.
- Copia confiable del código sin SQLite, secretos, PDF privados ni entorno virtual.
- Espacio y permisos de escritura en la carpeta nueva y un directorio privado.
- Acceso a los paquetes fijados en [requirements.txt](../requirements.txt).
- Caddy 2 con `skip_install_trust`, instalado por un canal confiable y en `PATH`.
- OpenSSH solo si se necesita el canal de administración; no es requisito para
  las funciones Django. Su preparación es un procedimiento separado:
  [SSH](SSH.md).

No usar una política global de ejecución sin restricciones para ejecutar
scripts. Revisar su procedencia y aplicar la política autorizada del equipo.

## 3. Código y entorno virtual

Colocar primero el código en una carpeta nueva; la siguiente ruta es ilustrativa:

```powershell
Set-Location 'C:\Proyectos\PlataformaSeguraNueva'
if (Test-Path -LiteralPath .\db.sqlite3) { throw 'Existe una base: no es una instalacion vacia.' }
if (Test-Path -LiteralPath .\.env) { throw 'Existe configuracion: revisar antes de continuar.' }
if (Test-Path -LiteralPath .\venv) { throw 'Existe un entorno virtual: no sobrescribir.' }

py -3.13 -m venv venv
if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno.' }
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Fallo la instalacion de dependencias.' }
.\venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Hay dependencias incompatibles.' }
```

No es necesario activar el entorno: se invoca su intérprete explícitamente.
No cambiar versiones silenciosamente si una dependencia no está disponible;
registrar el error y revisar compatibilidad en un entorno separado.

## 4. Almacenamiento y secretos propios

Ejecutar los bloques siguientes en **la misma consola**, únicamente después de
confirmar que es la instalación vacía. La ubicación se deriva del usuario actual,
sin utilizar rutas personales del proyecto recuperado.

```powershell
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security
$base = Join-Path $env:LOCALAPPDATA 'ProyectoFinalLocal'
$keyId = 'rsa-local-2026'  # Identificador ilustrativo de esta instalacion nueva.
if (Test-Path -LiteralPath $base) { throw 'El destino privado ya existe; no sobrescribir.' }
if ($base.StartsWith((Get-Location).Path.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'El almacenamiento privado debe quedar fuera del proyecto.'
}
New-Item -ItemType Directory -Path $base | Out-Null
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $base /inheritance:r /grant:r ("*{0}:(OI)(CI)F" -f $sid) '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron restringir las ACL; no crear secretos.' }

$catalogo = Join-Path $base 'catalogo'
$claves = Join-Path $base $keyId
$publicas = Join-Path $claves 'publicas'
New-Item -ItemType Directory -Path $catalogo,$claves,$publicas | Out-Null
$djangoBlob = Join-Path $base 'django-secret.dpapi'
$passwordBlob = Join-Path $claves 'password.dpapi'

function New-RandomText([int]$Length) {
    $bytes = New-Object byte[] $Length
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    } finally {
        [Array]::Clear($bytes, 0, $bytes.Length)
        $rng.Dispose()
    }
}

function Protect-NewText([string]$Path, [string]$Text) {
    $plain = [Text.Encoding]::UTF8.GetBytes($Text)
    try {
        $protected = [Security.Cryptography.ProtectedData]::Protect(
            $plain, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($protected, 0, $protected.Length) }
        finally { $stream.Dispose() }
    } finally {
        [Array]::Clear($plain, 0, $plain.Length)
    }
}

$djangoSecret = New-RandomText 48
$rsaPassword = New-RandomText 32
Protect-NewText $djangoBlob $djangoSecret
Protect-NewText $passwordBlob $rsaPassword
$djangoSecret = $null
```

El formato coincide con el lanzador: blobs DPAPI **binarios**, que al
descifrarse contienen texto UTF-8. No usar `ConvertFrom-SecureString` como
sustituto de este formato. Las ACL se restringen antes de guardar secretos.
No imprimir las variables secretas ni usar transcripciones para capturarlas.

### 4.1 Generar RSA cifrada de 3072 bits

El siguiente bloque usa la contraseña recién generada mediante el entorno
temporal del proceso, nunca en argumentos de línea de comandos ni en `.env`.
No cambia claves existentes y abre los archivos en modo de creación exclusiva.

```powershell
$names = @('PROVISION_RSA_ROOT', 'PROVISION_RSA_ID', 'PROVISION_RSA_PASSWORD')
$saved = @{}
foreach ($name in $names) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
try {
    $env:PROVISION_RSA_ROOT = $claves
    $env:PROVISION_RSA_ID = $keyId
    $env:PROVISION_RSA_PASSWORD = $rsaPassword
    @'
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

root = Path(os.environ["PROVISION_RSA_ROOT"])
key_id = os.environ["PROVISION_RSA_ID"]
password = os.environ["PROVISION_RSA_PASSWORD"].encode("utf-8")
private_path = root / "privada.pem"
public_path = root / "publicas" / (key_id + ".pem")
if private_path.exists() or public_path.exists():
    raise SystemExit("Destino existente: no sobrescribir claves.")
key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
with private_path.open("xb") as stream:
    stream.write(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    ))
with public_path.open("xb") as stream:
    stream.write(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
loaded = serialization.load_pem_private_key(private_path.read_bytes(), password=password)
public = serialization.load_pem_public_key(public_path.read_bytes())
if loaded.key_size != 3072 or loaded.public_key().public_numbers() != public.public_numbers():
    raise SystemExit("La pareja RSA generada no es valida.")
print("Pareja RSA cifrada de 3072 bits generada y comprobada.")
'@ | .\venv\Scripts\python.exe -B -
    if ($LASTEXITCODE -ne 0) { throw 'La provision RSA no termino correctamente.' }
} finally {
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
    $rsaPassword = $null
}
```

Si falla una etapa, detenerse y revisar el destino parcial; no presentarlo como
aprovisionado ni reintentar sobrescribiendo. La limpieza de variables reduce su
permanencia, pero no garantiza borrado absoluto de cadenas en memoria.

## 5. Configurar `.env`

```powershell
if (Test-Path -LiteralPath .\.env) { throw 'El archivo .env ya existe: no sobrescribir.' }
Copy-Item -LiteralPath .\.env.example -Destination .\.env -ErrorAction Stop
notepad.exe .\.env
```

El paso 3 exige que `.env` no exista. Editar las rutas ilustrativas de la
[plantilla](../.env.example) para que correspondan a los destinos recién creados:

| Variable | Valor de la instalación nueva |
| --- | --- |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_LOCAL_HTTPS` | `true` |
| `DJANGO_ALLOWED_HOSTS` | `localhost` |
| `DJANGO_PRIVATE_CATALOG_ROOT` | Ruta absoluta contenida en `$catalogo`. |
| `DJANGO_RECEIPTS_KEY_ID` | `rsa-local-2026`, el mismo `$keyId` de la generación. |
| `DJANGO_RECEIPTS_PRIVATE_KEY_PATH` | Ruta absoluta de `privada.pem` dentro de `$claves`. |
| `DJANGO_RECEIPTS_PUBLIC_KEYS_DIR` | Ruta absoluta contenida en `$publicas`. |
| `DJANGO_SECRET_KEY_DPAPI_PATH` | Ruta absoluta contenida en `$djangoBlob`. |
| `DJANGO_RECEIPTS_PASSWORD_DPAPI_PATH` | Ruta absoluta contenida en `$passwordBlob`. |

Usar los valores de las variables de PowerShell, **no pegar sus nombres
literalmente** en `.env`; `python-dotenv` no evalúa expresiones PowerShell.
Se admiten comillas simples alrededor de rutas Windows. No añadir
`DJANGO_SECRET_KEY` ni `DJANGO_RECEIPTS_PRIVATE_KEY_PASSWORD`, ni siquiera vacías:
el lanzador rechaza su presencia en el archivo.

La aplicación carga `.env` desde la raíz con `override=False`: el entorno
preexistente tiene prioridad. Revisar variables heredadas si el resultado no
coincide con el archivo; no imprimir sus valores secretos.

## 6. Inicializar exclusivamente la base nueva

El lanzador exige que SQLite exista, por lo que primero se prepara la base
vacía. Este bloque utiliza el secreto recién protegido para los comandos de
gestión y restaura el entorno al terminar. No configura pagos reales.

```powershell
if (Test-Path -LiteralPath .\db.sqlite3) { throw 'La base ya existe: no ejecutar esta inicializacion.' }
$previousSecret = [Environment]::GetEnvironmentVariable('DJANGO_SECRET_KEY', 'Process')
$plain = [Security.Cryptography.ProtectedData]::Unprotect(
    [IO.File]::ReadAllBytes($djangoBlob), $null,
    [Security.Cryptography.DataProtectionScope]::CurrentUser
)
try {
    $env:DJANGO_SECRET_KEY = [Text.Encoding]::UTF8.GetString($plain)
    [Array]::Clear($plain, 0, $plain.Length)
    .\venv\Scripts\python.exe -B manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la inicializacion de la base nueva.' }
    .\venv\Scripts\python.exe -B manage.py createsuperuser
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la creacion del administrador nuevo.' }
    .\venv\Scripts\python.exe -B manage.py collectstatic --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la preparacion de estaticos publicos.' }
} finally {
    [Array]::Clear($plain, 0, $plain.Length)
    [Environment]::SetEnvironmentVariable('DJANGO_SECRET_KEY', $previousSecret, 'Process')
}
```

No usar `makemigrations`: el proyecto ya incluye sus migraciones. Introducir
credenciales nuevas mediante los prompts, nunca en documentación ni argumentos.
El superusuario recibe ADMINISTRADOR por defecto; crear/asignar OPERADOR desde
la administración no implica otorgarle `is_staff` o `is_superuser`.

## 7. Validar y arrancar

```powershell
.\Iniciar-Seguro.ps1 -Check
if ($LASTEXITCODE -ne 0) { throw 'Revisar el error del inicio seguro.' }
.\Iniciar-Seguro.ps1
```

El chequeo valida rutas, DPAPI, pareja RSA, una firma efímera y configuración
Django sin crear registros. Ejecutar el script con manejo de errores de
PowerShell; los errores terminantes también deben detener el procedimiento.
No ejecutar otra instancia si 8000 está ocupado.

Iniciar Caddy en otra consola según [HTTPS_PKI](HTTPS_PKI.md). Validar CA,
nombre y redirección antes de autenticarse. Desde la aplicación nueva, crear
clientes y productos educativos propios según [el manual](MANUAL_USUARIO.md);
esta guía no importa históricos ni genera PDF por sí misma.

## 8. Recuperación y publicación

Copiar DPAPI a otra cuenta/laptop **no garantiza** recuperar los secretos.
Planificar una bóveda o recuperación autorizada separada y probarla, sin
publicar secretos. Las claves de SSH y de la CA Caddy son independientes de RSA.
Los respaldos ordinarios no contienen todo ese material.

Antes de GitHub, revisar archivos seleccionados y exclusiones siguiendo
[el checklist del README](../README.md#antes-de-publicar-en-github).
Ningún comando de esta guía debe ejecutarse sobre la instalación preservada.
