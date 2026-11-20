# HTTPS y PKI local con Caddy

[Índice general](../README.md) · [Instalación](INSTALACION.md)

## 1. Configuración implementada

El [Caddyfile](../Caddyfile) define:

- HTTPS en `localhost:8443`, con `tls internal` y enlace a `127.0.0.1`.
- HTTP en `localhost:8080`, también loopback, con redirección 308 a HTTPS.
- Proxy hacia Django en `127.0.0.1:8000`.
- Sustitución de `X-Forwarded-Proto` por `https` y eliminación de `Forwarded`,
  `X-Forwarded-Host` y `X-Forwarded-Port` antes de reenviar.
- Servicio de estáticos públicos desde `staticfiles`, no de PDF privados.
- API administrativa desactivada y `skip_install_trust`.

El perfil [Django](../config/settings.py) exige DEBUG=false cuando está activo
HTTPS local, acepta localhost, usa cookies Secure y mantiene CSRF.
No utiliza `X-Forwarded-Host`. HSTS es cero deliberadamente para no afectar otros
servicios locales; no es una política recomendada para producción.

## 2. CA y certificados

Caddy mantiene una CA local, con raíz e intermedia, y emite certificados de
desarrollo para el nombre configurado. La raíz pública es el ancla que el
cliente debe validar; las privadas de CA y servidor son secretas.
`skip_install_trust` evita instalar automáticamente la CA en Windows.

El certificado para `localhost` no debe aceptarse como identidad de otro nombre
o una dirección privada de un servidor futuro. No reutilizar claves de Caddy
para SSH, Django o comprobantes RSA.

La auditoría usó la raíz pública bajo:

```text
%APPDATA%\Caddy\pki\authorities\local\root.crt
```

La [guía manual histórica](../config/HTTPS_LOCAL.md) describe además un almacén
alternativo mediante `XDG_DATA_HOME`. No son rutas intercambiables: localizar el
almacén del proceso que realmente sirve TLS y mantenerlo persistente y con ACL.
No moverlo ni sustituirlo para seguir esta guía. No copiar su contenido a Git.

## 3. Arranque en un equipo preparado

En una consola, desde la raíz:

```powershell
.\Iniciar-Seguro.ps1
```

En otra, desde la misma raíz y con Caddy disponible:

```powershell
caddy.exe validate --config .\Caddyfile --adapter caddyfile
if ($LASTEXITCODE -ne 0) { throw 'Caddyfile invalido.' }
caddy.exe run --config .\Caddyfile --adapter caddyfile
```

No ejecutar otra instancia si los puertos ya están ocupados. No cambiar las
variables de almacén de un proceso preparado sin planificar su CA y certificados.
Detener los procesos iniciados interactivamente con Ctrl+C. El lanzador Django
no inicia ni detiene el Caddy que esté funcionando en otra consola.

## 4. Prueba de confianza sin cambiar Windows

Ejemplo para el almacén por defecto observado. Si no corresponde al equipo,
adaptar **solo la ruta del certificado público** después de comprobar el proceso.
Se validan cadena y hostname; no se usa un contexto sin verificación:

```powershell
$ca = Join-Path $env:APPDATA 'Caddy\pki\authorities\local\root.crt'
if (-not (Test-Path -LiteralPath $ca -PathType Leaf)) { throw 'Localizar la CA publica correcta.' }
$previousCa = [Environment]::GetEnvironmentVariable('LOCAL_CA_PEM', 'Process')
try {
    $env:LOCAL_CA_PEM = $ca
    @'
import os
import socket
import ssl

trusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
trusted.load_verify_locations(cafile=os.environ["LOCAL_CA_PEM"])
with socket.create_connection(("127.0.0.1", 8443), timeout=5) as raw:
    with trusted.wrap_socket(raw, server_hostname="localhost") as tls:
        print("Cadena y nombre validados:", tls.version())

untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
try:
    with socket.create_connection(("127.0.0.1", 8443), timeout=5) as raw:
        with untrusted.wrap_socket(raw, server_hostname="localhost"):
            raise SystemExit("ERROR: se acepto TLS sin la CA confiable.")
except ssl.SSLCertVerificationError:
    print("CA no confiable: rechazo correcto.")
'@ | .\venv\Scripts\python.exe -B -
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la comprobacion TLS.' }
} finally {
    [Environment]::SetEnvironmentVariable('LOCAL_CA_PEM', $previousCa, 'Process')
}
```

No ignorar advertencias del navegador ni instalar una raíz sin comprobar su
procedencia. La confianza explícita del ejemplo afecta solo a ese contexto
Python, no a Windows. Las conexiones TLS no solicitan páginas Django.

### Redirección

```powershell
curl.exe -q --noproxy '*' --resolve localhost:8080:127.0.0.1 `
    -sS -o NUL -w 'HTTP: %{http_code} %{redirect_url}\n' http://localhost:8080/
if ($LASTEXITCODE -ne 0) { throw 'Fallo la conexion HTTP local.' }
```

Se espera 308 y destino `https://localhost:8443/`. No seguir la redirección sin
validar la CA. Este comando no imprime cuerpos ni cookies.

## 5. Evidencia y límites de revocación

El [estado de entorno de auditoría](evidencias/auditoria/estado_entorno.json)
registra TLS 1.3, validación de CA/hostname, rechazo con almacén vacío y
redirección 308. Son pruebas del 19/11/2026, no una nueva ejecución al redactar
esta guía. Las cabeceras, CSRF y cookies se probaron con el cliente Django según
[el registro de pruebas](PRUEBAS_EVIDENCIAS.md).

No se ha demostrado una infraestructura de revocación con CRL/OCSP ni su
comprobación por los clientes de esta CA local. Un certificado con cadena y
fecha válidas no prueba ausencia de compromiso de su clave.
Si se compromete la CA, se necesita respuesta autorizada: retirar su confianza
de clientes afectados, reemplazar material y volver a establecer confianza
por un canal seguro. No confundir renovación con revocación comprobada.

`runserver`, CA de desarrollo, loopback y confianza en el proxy local no deben
presentarse como una solución de producción. Una VPN futura no elimina la
necesidad de validar TLS: [arquitectura propuesta](ARQUITECTURA_VPN_IPSEC.md).
