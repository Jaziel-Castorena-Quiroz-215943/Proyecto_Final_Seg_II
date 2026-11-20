# HTTPS local con Caddy en Windows

Esta guía conserva el procedimiento manual y un almacén Caddy alternativo.
Para el arranque automatizado y la evidencia actual consultar
[HTTPS y PKI](../docs/HTTPS_PKI.md). No cambiar el almacén de un Caddy ya
preparado para reproducir los ejemplos; todas las rutas de proyecto siguientes
son ilustrativas.

## Arquitectura y límites

- Caddy escucha únicamente en `127.0.0.1`: HTTPS en `localhost:8443` y
  redirección HTTP en `localhost:8080`. Su API de administración está apagada.
- Caddy emite un certificado para `localhost` con su CA local y sobrescribe
  `X-Forwarded-Proto` con `https` antes de enviar peticiones a Django en
  `127.0.0.1:8000`. Descarta `Forwarded`, `X-Forwarded-Host` y
  `X-Forwarded-Port`. No configura proxies entrantes de confianza.
- Con `DJANGO_LOCAL_HTTPS=true`, Django exige `DJANGO_DEBUG=false`, confía en
  ese encabezado de protocolo, redirige HTTP, usa cookies Secure y no confía en
  `X-Forwarded-Host`. HSTS permanece desactivado para no afectar otros servicios
  en `localhost`. CSRF sigue habilitado y comprueba el origen HTTPS y el token.
- **Loopback no aísla usuarios locales:** otro proceso del equipo puede acceder
  directamente al puerto 8000 y falsificar encabezados. Este perfil solo es
  apropiado en un equipo o entorno local de confianza. No expongas Django ni
  Caddy a la red ni uses esta configuración como frontera de seguridad entre
  usuarios locales. El servidor `runserver` tampoco es apto para producción.
- Caddy sirve únicamente el directorio `staticfiles` bajo `/static/`; el resto
  se envía a Django. No configura un servidor de archivos para medios, claves
  privadas, PDFs originales, la CA ni el directorio del proyecto.

## Preparación manual

1. Obtén Caddy por un canal oficial y verifica el binario según la política de tu
   organización. Este proyecto **no instala ni descarga Caddy**. Añádelo a tu
   `PATH` o sustituye `caddy.exe` en los comandos por su ruta absoluta. Se usa
   Caddy 2 con soporte para `skip_install_trust`; valida el archivo antes de
   arrancar. La base de datos debe estar preparada previamente por el usuario:
   estos pasos no ejecutan migraciones.

2. Usa una clave Django estable, larga y aleatoria. En una primera consola
   PowerShell, desde el proyecto, configura el perfil. La contraseña introducida
   no se imprime; queda en el entorno de este proceso y sus hijos. No uses
   `setx` para guardarla. Se carga `.env` desde la raíz con `override=False`;
   un archivo dentro de `config` no se carga automáticamente.

   ```powershell
   Set-Location 'C:\Proyectos\PlataformaSeguraNueva'
   $env:DJANGO_DEBUG = 'false'
   $env:DJANGO_LOCAL_HTTPS = 'true'
   $env:DJANGO_ALLOWED_HOSTS = 'localhost'
   $secret = Read-Host 'DJANGO_SECRET_KEY estable' -AsSecureString
   if ($secret.Length -eq 0) { throw 'La clave está vacía.' }
   $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
   try {
       $env:DJANGO_SECRET_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
   } finally {
       [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
       $secret.Dispose()
   }
   ```

   Para pagos y PDFs, configura también las variables existentes descritas en
   [comprobantes](../receipts/README.md) y [catálogo](../catalog/README.md).
   No reutilices la clave RSA de comprobantes como clave TLS ni como
   `DJANGO_SECRET_KEY`.

3. Si necesitas los estáticos del administrador, ejecuta manualmente:

   ```powershell
   & '.\venv\Scripts\python.exe' manage.py collectstatic --noinput
   ```

   Esto escribe en `staticfiles`; revisa previamente su contenido si ya existe.
   Solo deben colocarse allí archivos estáticos públicos de confianza, sin
   enlaces a archivos privados. Después arranca Django en la misma consola:

   ```powershell
   & '.\venv\Scripts\python.exe' manage.py runserver 127.0.0.1:8000 --noreload
   ```

4. En una **segunda consola**, desde el mismo directorio, fija un almacén Caddy
   separado y persistente, valida y arranca:

   ```powershell
   Set-Location 'C:\Proyectos\PlataformaSeguraNueva'
   $env:XDG_DATA_HOME = Join-Path $env:LOCALAPPDATA 'ProyectoFinalCaddy\Data'
   $env:XDG_CONFIG_HOME = Join-Path $env:LOCALAPPDATA 'ProyectoFinalCaddy\Config'
   caddy.exe validate --config .\Caddyfile --adapter caddyfile
   caddy.exe run --config .\Caddyfile --adapter caddyfile
   ```

   Detén cada proceso con Ctrl+C. El directorio de datos contendrá **claves
   privadas de la CA y certificados**. Mantén ACL y respaldos restringidos al
   usuario de Caddy y administradores autorizados; no lo publiques ni lo agregues
   al proyecto. Una CA cuya clave privada se filtra deja de ser confiable. El
   certificado raíz público se encontrará en:

   ```text
   %LOCALAPPDATA%\ProyectoFinalCaddy\Data\caddy\pki\authorities\local\root.crt
   ```

   La CA de Caddy y sus certificados se generan al usar el servidor; no se han
   generado con estos cambios. `skip_install_trust` evita cualquier instalación
   automática en almacenes de confianza.

## Pruebas TLS sin modificar la confianza de Windows

Con ambos procesos en ejecución, abre una tercera consola. La siguiente prueba
usa la CA **solo en un contexto TLS de Python** y una segunda conexión con un
almacén vacío. No utiliza `--insecure` y no cambia la confianza del equipo:

```powershell
Set-Location 'C:\Proyectos\PlataformaSeguraNueva'
$env:LOCAL_CA_PEM = Join-Path $env:LOCALAPPDATA 'ProyectoFinalCaddy\Data\caddy\pki\authorities\local\root.crt'
@'
import os
import socket
import ssl

trusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
trusted.load_verify_locations(cafile=os.environ['LOCAL_CA_PEM'])
with socket.create_connection(('127.0.0.1', 8443), timeout=5) as raw:
    with trusted.wrap_socket(raw, server_hostname='localhost') as tls:
        print('CA explicita confiable:', tls.version())

untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
try:
    with socket.create_connection(('127.0.0.1', 8443), timeout=5) as raw:
        with untrusted.wrap_socket(raw, server_hostname='localhost'):
            raise SystemExit('ERROR: se acepto un certificado sin CA confiable')
except ssl.SSLCertVerificationError:
    print('CA no confiable: rechazada correctamente')
'@ | & '.\venv\Scripts\python.exe' -
```

La primera conexión debe validar la cadena y el nombre `localhost`; la segunda
debe rechazarla. Si falla la primera, comprueba la ruta del `root.crt`, el
proceso y su almacén; no desactives la verificación. Un navegador que no confíe
en esa CA mostrará una advertencia: no la ignores. Confiar persistentemente en
una CA es una decisión administrativa separada y no forma parte de estos pasos.

También puedes probar el proxy sin mostrar cookies:

```powershell
$ca = Join-Path $env:LOCALAPPDATA 'ProyectoFinalCaddy\Data\caddy\pki\authorities\local\root.crt'
curl.exe -q --noproxy '*' --resolve localhost:8443:127.0.0.1 --cacert $ca `
  -sS -o NUL -w 'HTTPS: %{http_code}\n' https://localhost:8443/accounts/login/
curl.exe -q --noproxy '*' --resolve localhost:8443:127.0.0.1 --cacert $ca `
  -H 'X-Forwarded-Proto: http' -sS -o NUL -w 'Encabezado sustituido: %{http_code}\n' `
  https://localhost:8443/accounts/login/
curl.exe -q --noproxy '*' --resolve localhost:8080:127.0.0.1 `
  -sS -o NUL -w 'HTTP: %{http_code} %{redirect_url}\n' http://localhost:8080/
```

Se espera `200`, `200` y redirección `308` a HTTPS, respectivamente. El segundo
resultado comprueba que Caddy sustituye el protocolo suministrado por el cliente
en la ruta HTTPS. Las pruebas automatizadas de Django verifican redirección,
CSRF y cookies Secure, pero no sustituyen estas pruebas reales con Caddy y TLS.

## Fuentes

- [HTTPS automático y CA local de Caddy](https://caddyserver.com/docs/automatic-https)
- [Opciones globales de Caddy](https://caddyserver.com/docs/caddyfile/options)
- [Cabeceras del proxy de Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#headers)
