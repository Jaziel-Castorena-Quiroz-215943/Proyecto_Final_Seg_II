# SSH con claves Ed25519

[Índice general](../README.md) · [VPN propuesta](ARQUITECTURA_VPN_IPSEC.md)

## 1. Función y estado

OpenSSH para Windows protege la administración del sistema, independientemente
del inicio de sesión Django. El proyecto reporta autenticación con Ed25519.
La revisión comprobó servicio activo, configuración legible y escucha local;
**no repitió una sesión SSH Ed25519 ni leyó el archivo protegido de claves
autorizadas de administradores**.

Directivas observadas, mostradas solo como descripción y no para sobrescribir
la configuración:

```text
Port 22
ListenAddress 127.0.0.1
PubkeyAuthentication yes
PasswordAuthentication no
KbdInteractiveAuthentication no
```

Las claves autorizadas usan el archivo de usuario y, para administradores,
el archivo específico bajo `%ProgramData%\ssh`. Sus ACL y el contexto de la
cuenta importan: no cambiar permisos para eludir un error de lectura.

## 2. Por qué no hay acceso remoto actual

`127.0.0.1:22` solo recibe conexiones originadas en la propia máquina.
Desde otra computadora, localhost identifica esa otra computadora.
Una VPN o una apertura de firewall no cambia la dirección de escucha.

Para acceso remoto futuro se necesitarían interfaz privada de gestión,
enrutamiento, restricciones de firewall y un cambio autorizado de escucha.
No se realizaron. La [propuesta VPN/IPsec](ARQUITECTURA_VPN_IPSEC.md)
detalla el diseño y sus pruebas pendientes.

## 3. Gestión de claves

Ed25519 tiene un par de usuario y SSH también utiliza claves de host del
servidor: no son la misma identidad. Verificar la huella de host por un canal
confiable antes de aceptarla; no desactivar `StrictHostKeyChecking` ni ignorar
un cambio de clave.

La privada del usuario permanece en su equipo, con permisos restringidos y
frase de paso. El servidor recibe únicamente la pública autorizada.
No poner privadas en el proyecto, `.env`, respaldos ordinarios o GitHub.
No reutilizar el par RSA de comprobantes o claves TLS como credenciales SSH.

Solo para una cuenta/laboratorio nuevo autorizado, si se necesitan claves
propias y no existe el destino:

```powershell
$ErrorActionPreference = 'Stop'
$sshDirectory = Join-Path $env:USERPROFILE '.ssh'
if (-not (Test-Path -LiteralPath $sshDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $sshDirectory | Out-Null
}
$key = Join-Path $sshDirectory 'id_ed25519_proyecto'
if ((Test-Path -LiteralPath $key) -or (Test-Path -LiteralPath ($key + '.pub'))) {
    throw 'La clave ya existe: no sobrescribir.'
}
ssh-keygen.exe -t ed25519 -a 100 -f $key
if ($LASTEXITCODE -ne 0) { throw 'Fallo la generacion de la clave nueva.' }
```

Introducir frase de paso mediante el prompt, no como argumento. La instalación
de la pública en la cuenta correcta y la revisión de ACL requieren un
procedimiento administrativo autorizado separado. Estos comandos no se
ejecutaron como parte de la documentación ni se copiaron claves existentes.

## 4. Comprobaciones de lectura

```powershell
Get-Service -Name sshd
Get-NetTCPConnection -State Listen -LocalPort 22 |
    Select-Object LocalAddress,LocalPort
Get-Content -LiteralPath (Join-Path $env:ProgramData 'ssh\sshd_config') |
    Select-String '^\s*(Port|ListenAddress|PubkeyAuthentication|PasswordAuthentication|KbdInteractiveAuthentication)\s+'
```

No elevar permisos ni cambiar el servicio si una consulta no está autorizada.
Leer directivas no sustituye a evaluar todas las condiciones `Match` y la
configuración efectiva. El intento anterior de `sshd -T` no concluyó por
`no hostkeys available -- exiting`; no demuestra que el servicio activo carezca
de hostkeys. Véanse sus límites en [la documentación VPN](ARQUITECTURA_VPN_IPSEC.md).

## 5. Pruebas de sesión pendientes

En un laboratorio autorizado, con cuenta de prueba, pública instalada y huella
de host verificada, un ejemplo de prueba positiva sería:

```powershell
ssh.exe -o PreferredAuthentications=publickey `
    -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no `
    -o IdentitiesOnly=yes -i "$env:USERPROFILE\.ssh\id_ed25519_proyecto" `
    cuenta-laboratorio@127.0.0.1
```

La frase de paso de la privada local, si se pide, no es la contraseña de la
cuenta del servidor. No sustituir el ejemplo por credenciales de otro usuario.

| Prueba futura | Resultado esperado | Estado de la evidencia existente |
| --- | --- | --- |
| Cuenta y clave Ed25519 autorizadas | Sesión aceptada tras validar host. | Pendiente de nueva ejecución independiente. |
| Clave no autorizada | Rechazo sin alternativa por contraseña. | Pendiente; no hacer fuerza bruta. |
| Autenticación solo con contraseña | Rechazo. | Directivas deshabilitadas leídas; rechazo dinámico no ejecutado. |
| Acceso desde otra máquina | No alcanzable con el enlace loopback actual. | No se realizó prueba remota; escucha local observada. |

Una conexión negativa puede escribir logs; incluso estas pruebas deben
reservarse al laboratorio y no confundirse con consultas de solo lectura.
La [evidencia de entorno](evidencias/auditoria/estado_entorno.json) registra
configuración y escuchas, no una autenticación nueva.
