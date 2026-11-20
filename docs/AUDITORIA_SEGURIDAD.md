# Auditoría final de seguridad

**Proyecto:** Plataforma Segura de Venta y Distribución de Contenido Digital.  
**Asignatura:** Seguridad de la Información II.  
**Fecha de ejecución:** 19 de noviembre de 2026, zona horaria UTC−06:00.  
**Entorno examinado:** Windows, Python 3.13.7, Django 6.1.3 y SQLite.

## 1. Introducción

La plataforma administra cuentas, PDF privados, compras simuladas, comprobantes
firmados y descargas con fingerprinting. Su seguridad depende tanto de impedir
accesos indebidos como de conservar los documentos y las claves públicas que
permiten atender y verificar operaciones históricas.

Esta auditoría combina inspección del código, pruebas con datos sintéticos y
consultas de solo lectura sobre el estado real. Distingue controles aprobados,
limitaciones de recuperación confirmadas y verificaciones todavía pendientes.
No constituye una certificación ni una garantía de ausencia de vulnerabilidades.

## 2. Objetivo

Evaluar autenticación, autorización, archivos privados, transacciones,
criptografía, comunicaciones, trazabilidad y recuperación sin cambiar los datos
ni las configuraciones originales. Documentar hallazgos reproducibles y
recomendaciones, sin corregir registros históricos durante la auditoría.

## 3. Alcance

### 3.1 Componentes inspeccionados

- [Configuración y middleware Django](../config/settings.py).
- Aplicaciones [accounts](../accounts), [catalog](../catalog), [cart](../cart),
  [orders](../orders), [receipts](../receipts) y [security](../security), incluidas
  sus pruebas, permisos y registro de eventos.
- [Caddyfile](../Caddyfile), [lanzador seguro](../Iniciar-Seguro.ps1),
  [ejemplo de entorno](../.env.example), reglas de
  [.gitignore](../.gitignore) y documentación de
  [HTTPS local](../config/HTTPS_LOCAL.md).
- Directivas legibles de OpenSSH para Windows y escuchas TCP locales.
- [Arquitectura VPN/IPsec](ARQUITECTURA_VPN_IPSEC.md), que es una propuesta.
- [Respaldo](../scripts/backup.ps1), [restauración](../scripts/restore.ps1),
  [validador confiable](../scripts/recovery.py), manifiesto existente y
  [documentación de recuperación](RESPALDO_RESTAURACION.md).

### 3.2 Estado real consultado

| Registro | Base original | Cada una de las tres restauraciones revalidadas |
| --- | ---: | ---: |
| Usuarios | 3 | 3 |
| Productos | 6 | 6 |
| Órdenes | 8 | 8 |
| Pagos simulados | 7 | 7 |
| Comprobantes | 5 | 5 |
| Fingerprints | 4 | 4 |

Los conteos son agregados: no se publican identidades ni contenido privado.
El estado actual sustituye, para esta auditoría, los conteos de etapas anteriores.

### 3.3 Exclusiones y límites

No se ejecutaron ataques destructivos, pruebas contra servicios externos,
migraciones sobre la base real, cambios de roles, emisión de comprobantes reales
ni descargas HTTP autenticadas sobre la aplicación activa. No se descifraron
DPAPI ni claves privadas, no se instalaron servicios y no se cambió Windows.

No se realizó un análisis exhaustivo de dependencias/CVE, fuerza bruta, carga,
malware en documentos, historial Git o infraestructura de producción. Las
pruebas locales no demuestran seguridad de un despliegue público futuro.

## 4. Metodología

1. Inspección en lectura de configuración, rutas, permisos, servicios y pruebas.
2. Captura inicial de SHA-256 de 22 archivos originales controlados.
3. Ejecución de la suite Django y tres pruebas suplementarias de auditoría con
   usuarios, PDF y claves sintéticos. Se confirmó una base de pruebas SQLite
   **en memoria**. Las migraciones que aparecen en el log se aplican solamente
   a esa base temporal, nunca a la base original.
4. Ejecución de cinco pruebas sintéticas del procedimiento de recuperación.
5. Apertura de SQLite real mediante URI `mode=ro`, con consultas agregadas.
   El ORM usado para verificar comprobantes también se configuró en lectura.
6. Invocación directa de los lectores/verificadores confiables, sin pasar por
   vistas que escriben eventos en la base activa.
7. Handshake TLS hacia loopback con CA pública explícita y prueba negativa
   sin CA confiable. La única solicitud HTTP al servicio activo fue al puerto
   8080 para comprobar la redirección de Caddy; no llegó a Django.
8. Revalidación de respaldos y restauraciones **ya existentes**. En esta
   auditoría no se creó otro respaldo real ni otra restauración real: los
   ejercicios reales anteriores están documentados por separado.
9. Comparación final de las huellas originales y conservación de evidencia
   agregada, sin secretos, cookies, tokens ni contenido de PDF.

**Resultado automatizado:** 56/56 pruebas Django y 5/5 pruebas de recuperación
aprobadas. El código de salida final de la suite Django fue `0`.
La primera captura tuvo un problema de codificación al imprimir el log en
consola, después de que la suite terminara satisfactoriamente; se repitió con
UTF-8 explícito y se conservó el [log final](evidencias/auditoria/tests_django_final.txt).
No se trató de un fallo de un control de la aplicación.

## 5. Criterios de evaluación

- **Control de acceso:** autenticación, autorización y separación de roles.
- **Protección web:** CSRF, sesiones, cookies y cabeceras de seguridad.
- **Archivos y comunicaciones:** tratamiento de contenido no confiable,
  privacidad de las descargas y uso de HTTPS.
- **Recuperación:** conservación de datos y archivos, integridad de respaldos
  y comprobación de restauraciones aisladas.
- **Gestión criptográfica:** conservación de claves públicas históricas y
  protección del material secreto.
- **Criterios funcionales del proyecto:** una descarga debe corresponder al
  propietario, pago aprobado y versión exacta comprada; una firma histórica debe
  verificarse con su clave pública original confiable, no con una clave nueva.

La severidad es cualitativa y considera impacto observado, alcance local y
controles compensatorios; no se
asigna CVSS a limitaciones de datos sin una explotación demostrada.

## 6. Inventario de controles

| Área | Control observado | Evidencia y limitación |
| --- | --- | --- |
| Autenticación | Django, validación de formularios y protección de campos de privilegio | Pruebas de registro, login, reset y CSRF aprobadas con fixtures. |
| Autorización | Roles explícitos y comprobaciones de propietario/superusuario | CLIENTE compra; OPERADOR gestiona catálogo y consulta órdenes; el rol ADMINISTRADOR por sí solo no concede superusuario. |
| Administración | Gestión sensible restringida a superusuario | Redirección de anónimos y rechazo de roles ordinarios comprobados. Un superusuario no hereda la función OPERADOR del catálogo por diseño. |
| Sesiones y CSRF | Cookies Secure, HttpOnly y SameSite=Lax; middleware CSRF | Login sintético HTTPS aprobado; negativos sin token y origen incorrecto rechazados. |
| PDF privados | Almacenamiento fuera del proyecto, sin URL pública y validación de archivos | Extensión/cabecera, tamaño, cifrado, estructura y hash cubiertos por pruebas; no equivalen a análisis antimalware. |
| Carrito y pagos | Cálculo del servidor, cotización firmada, expiración e idempotencia | Manipulación, concurrencia, propiedad y rollback probados. Los pagos son simulados. |
| Comprobantes | JSON canónico, SHA-256, RSA-PSS y validación contra orden/pago | Tres firmas reales válidas; dos pendientes por clave pública ausente. No son PDF: su cuerpo y firma están en SQLite. |
| Claves | Selección por identificador validado y privadas fuera del proyecto | Pública `rsa-demo-2026` de 3072 bits leída y comprobada; privada y DPAPI no descifrados. |
| Fingerprinting | Original exacto por línea, marca/token y hash del PDF emitido | Personalizados se generan en memoria; se conserva metadato en SQLite. No es DRM ni garantiza resistir la eliminación de la marca. |
| Eventos | Acciones de autenticación, órdenes, pagos, comprobantes y descargas | Trece tipos presentes en datos reales; altas sintéticas comprobadas en pruebas. No se demostró almacenamiento externo inmutable. |
| HTTPS | Caddy con CA local, certificado de desarrollo y redirección | TLS 1.3 con hostname y CA validados; sin esa CA se rechaza; HTTP devuelve 308. |
| Django local | DEBUG=false, hosts localhost, proxy de confianza y cabeceras | `manage.py check` aprobado con perfil HTTPS y secreto efímero; cabeceras probadas con cliente Django, no mediante login real. |
| Exposición | Puertos 22, 8000, 8080 y 8443 en 127.0.0.1 | Observación de sockets real. No prueba resistencia frente a procesos locales maliciosos. |
| SSH | Clave pública habilitada, contraseña e interacción por teclado deshabilitadas | Directivas leídas y puerto local observado; no se inició sesión nueva ni se validó toda la configuración efectiva. |
| VPN/IPsec | Arquitectura IKEv2/ESP documentada | No implementada ni probada; SSH en loopback no admite acceso desde una VPN remota actual. |
| Respaldos | API consistente SQLite, manifiesto, SHA-256 externo y validación restrictiva | Paquete y tres restauraciones revalidados; secretos excluidos. Se preservan también los faltantes anteriores. |
| Secretos y Git | `.env` sin valores de las dos variables sensibles; DPAPI separado y reglas de exclusión | Trece casos de exclusión comprobados; no existe repositorio Git activo para auditar archivos seguidos o historial. |

El lanzador se inspeccionó, pero no se ejecutó: iniciar otra instancia o
descifrar secretos no era necesario para esta auditoría.

## 7. Matriz de pruebas

El [registro CSV](evidencias/auditoria/matriz_pruebas.csv) incluye identificador,
procedimiento, resultado esperado, resultado obtenido, estado y evidencia.

| ID | Control | Resultado real | Estado |
| --- | --- | --- | --- |
| AUD-T01 | Administración anónima | Login requerido en rutas protegidas. | Aprobada |
| AUD-T02 | CLIENTE/OPERADOR/ADMINISTRADOR | Matriz de permisos y separación de superusuario verificadas. | Aprobada |
| AUD-T03 | Descargas privadas | Propietario, pago, rol y ausencia de URL pública comprobados. | Aprobada |
| AUD-T04 | Órdenes ajenas y pagos | Acceso cruzado rechazado; precios e idempotencia probados. | Aprobada |
| AUD-T05 | CSRF y sesión | Negativos rechazados; cookies y login sintéticos correctos. | Aprobada |
| AUD-T06 | HTTPS y configuración | DEBUG=false, TLS 1.3, CA validada/rechazada según confianza y 308; cabeceras probadas. | Aprobada |
| AUD-T07 | Firma e integridad | Tres comprobantes reales válidos; fixtures manipulados rechazados. | Aprobada, alcance disponible |
| AUD-T08 | PDF y fingerprint | Alteraciones y copia de token rechazadas en pruebas sintéticas. | Aprobada |
| AUD-T09 | Eventos | Casos automatizados aprobados y trece tipos reales consultados. | Aprobada |
| AUD-T10 | Exclusiones y secretos | Trece reglas; variables sensibles vacías en archivos de entorno; textos sin bloques PEM privados. | Aprobada, alcance acotado |
| AUD-T11 | Recuperación de lo incluido | Ocho archivos verificados; tres restauraciones revalidadas; copia alterada rechazada. | Aprobada, con faltantes declarados |
| AUD-T12 | Originales históricos | Cuatro PDF distintos ausentes; cuatro líneas pagadas afectadas. | No cumple: AUD-01 |
| AUD-T13 | Versionado histórico | Cuatro líneas sin versión, tres pagadas. | No cumple: AUD-02 |
| AUD-T14 | Verificación histórica completa | Dos firmas sin pública `rsa-2026`. | No cumple: AUD-03 |
| AUD-T15 | SSH y escuchas | Directivas leídas y cuatro puertos solo loopback. | Aprobada, lectura |
| AUD-T16 | Login nuevo SSH Ed25519 | No ejecutado; archivo autorizado protegido no inspeccionado. | Pendiente |
| AUD-T17 | Historial Git | No hay repositorio activo; no puede comprobarse exposición previa. | Pendiente |
| AUD-T18 | DPAPI en otro equipo | No se descifraron ni migraron secretos. | Pendiente |
| AUD-T19 | VPN operativa futura | No instalada ni probada; fuera del despliegue local actual. | Pendiente, futura |
| AUD-T20 | Originales intactos | SHA-256 de 22 archivos sin cambios; SQLite abierta en lectura. | Aprobada |

**Balance de la matriz:** 13 aprobadas, 3 no cumplen por limitaciones históricas
y 4 pendientes. Esto no es el número de casos automatizados: esos fueron 61,
todos aprobados. Los rechazos deliberados de firmas/PDF/respaldos manipulados son
resultados correctos de controles, no pruebas fallidas.

### 7.1 Evidencias conservadas

| Evidencia | Contenido no sensible |
| --- | --- |
| [tests_django_final.txt](evidencias/auditoria/tests_django_final.txt) | Los 56 casos, base en memoria y código final 0. |
| [tests_recuperacion.txt](evidencias/auditoria/tests_recuperacion.txt) | Cinco casos de recuperación con fixtures sintéticos. |
| [estado_datos.json](evidencias/auditoria/estado_datos.json) | Conteos, faltantes, impacto en líneas pagadas, firmas y tres restauraciones. |
| [estado_entorno.json](evidencias/auditoria/estado_entorno.json) | Perfil, 13 reglas Git, revisión de 117 textos, TLS y directivas SSH. |
| [invariancia_originales.json](evidencias/auditoria/invariancia_originales.json) | Resultado agregado de la comparación de 22 originales. |
| [matriz_pruebas.csv](evidencias/auditoria/matriz_pruebas.csv) | Registro completo de procedimientos y resultados. |
| [test_controles_auditoria.py](evidencias/auditoria/test_controles_auditoria.py) | Tres pruebas complementarias; credenciales sintéticas generadas solo en memoria. |
| [verificar_lectura.py](evidencias/auditoria/verificar_lectura.py) | Consulta real en lectura y revalidación de paquetes existentes. |
| [comprobar_entorno.py](evidencias/auditoria/comprobar_entorno.py) | Comprobaciones locales de entorno sin cambios de configuración. |

La lectura de textos para detectar bloques PEM no es una búsqueda exhaustiva
de todos los tipos de secretos. No se publican claves, DPAPI, valores secretos,
sesiones, nombres/correos reales, documentos privados ni cuerpos de comprobantes.

## 8. Hallazgos detallados

Los tres hallazgos siguientes son **limitaciones de disponibilidad, operación
y recuperación**. No demuestran escalamiento de privilegios, falsificación
criptográfica ni divulgación a usuarios no autorizados.

### AUD-01. PDF históricos referenciados no disponibles

- **Clasificación:** limitación de recuperación y disponibilidad.
- **Criterio:** conservar y restaurar el contenido asociado a las compras;
  mantener copias de archivos además de la base de datos.
- **Condición:** faltan **cuatro PDF distintos**, con **nueve referencias**:
  cuatro desde productos y cinco desde líneas con versión registrada.
  **Cuatro de esas cinco líneas** tienen orden PAID y pago SUCCESS.
- **Evidencia reproducible:** AUD-T12 y los contadores
  `distinct_missing_pdf_files`, `missing_product_pdf_references`,
  `missing_order_pdf_references` y `paid_missing_order_pdf_references` de
  [estado_datos.json](evidencias/auditoria/estado_datos.json).
  Ejecutar el script de lectura de la sección 10.1.
  Las cinco llamadas reales a
  [read_original](../security/fingerprinting.py), líneas 40–48, rechazaron
  correctamente los originales ausentes.
- **Causa identificada:** los archivos esperados no existen en el
  almacenamiento privado configurado.
  **Origen probable, no demostrado:** recuperación o traslado anterior que
  conservó SQLite pero no todo el almacenamiento. No se atribuye a un ataque.
- **Riesgo e impacto:** imposibilidad de generar ciertas descargas legítimas;
  un respaldo actual conserva los registros, pero no recupera bytes que ya
  estaban ausentes. Los contadores son de referencias/líneas, no de clientes
  u órdenes distintas.
- **Severidad:** **MEDIA**, por disponibilidad afectada de compras pagadas,
  con alcance acotado y rechazo seguro. No hay evidencia de exposición o
  entrega de un PDF incorrecto.
- **Recomendación:** localizar originales en una fuente confiable y comprobar
  su SHA-256 contra el registrado antes de proponer una recuperación autorizada.
  No sustituirlos por PDF nuevos ni cambiar hashes históricos para hacerlos
  coincidir. Si no existen, mantener explícita la limitación.
- **Estado:** **abierto**. No se regeneraron ni restauraron esos originales.

### AUD-02. Líneas históricas sin versión PDF de compra

- **Clasificación:** debilidad operativa heredada y limitación de recuperación.
- **Criterio:** preservar la asociación verificable entre cada compra y la
  versión exacta del documento; no inferirla a partir del producto actual.
- **Condición:** **cuatro líneas** no contienen una versión completa
  `pdf_name`/`pdf_sha256`; **tres** tienen orden PAID y pago SUCCESS.
- **Evidencia reproducible:** AUD-T13; contadores
  `unversioned_order_items`, `paid_unversioned_order_items` y
  `unversioned_read_original_rejected` de
  [estado_datos.json](evidencias/auditoria/estado_datos.json).
  Las cuatro invocaciones a
  [read_original](../security/fingerprinting.py), líneas 30–32, fueron rechazadas.
  El comportamiento HTTP 409 está cubierto por la suite sintética; no se
  solicitó una descarga real que escribiera un evento.
- **Causa identificada:** ausencia de metadatos de versión en esas filas.
  **Origen probable, no demostrado:** registros creados antes de incorporar
  versionado por línea. La existencia de una migración posterior no prueba
  por sí sola el origen de cada fila.
- **Riesgo e impacto:** no puede establecerse ni servir con certeza la versión
  adquirida, aunque el producto actual tenga un PDF. Copiar el archivo actual
  a los registros podría alterar su significado histórico.
- **Severidad:** **MEDIA**, por bloqueo confirmado de líneas pagadas y pérdida
  de trazabilidad de versión. El rechazo evita una entrega especulativa.
- **Recomendación:** buscar evidencia original que permita reconstruir la
  asociación y someter cualquier regularización a autorización separada.
  Sin evidencia verificable, documentar la excepción; no completar por
  adivinanza, ejecutar migraciones correctivas ni modificar compras históricas.
- **Estado:** **abierto**. Filas conservadas intactas.

### AUD-03. Clave pública histórica no disponible

- **Clasificación:** limitación de verificación criptográfica y recuperación.
- **Criterio:** conservar las claves públicas confiables necesarias durante
  el periodo de verificación de firmas.
- **Condición:** **dos de cinco comprobantes** usan `rsa-2026`, cuya clave
  pública no está disponible. Los **otros tres** se verificaron criptográficamente
  y contra sus relaciones de orden/pago. La pública actual `rsa-demo-2026`
  tiene 3072 bits y no sustituye a la histórica.
- **Evidencia reproducible:** AUD-T14;
  `missing_public_key_ids`, `receipts_unverifiable_missing_public_key` y
  `stored_receipts_verified_including_relationships` de
  [estado_datos.json](evidencias/auditoria/estado_datos.json).
  [public_key](../receipts/crypto.py), líneas 32–43, falla de forma explícita;
  [configuration_response](../receipts/views.py), líneas 40–42, devuelve 503.
  Ese 503 se comprobó con datos sintéticos, no mediante consulta HTTP real.
- **Causa identificada:** falta el archivo público histórico requerido.
  **Origen probable, no demostrado:** conservación incompleta del material
  público durante la recuperación anterior.
- **Riesgo e impacto:** no puede concluirse la autenticidad criptográfica de
  esos dos comprobantes con los materiales actuales. Sus filas y firmas se
  mantienen, pero no se ha demostrado ni validez ni falsificación.
- **Severidad:** **MEDIA**, por afectación acotada de verificación histórica.
  No se ha demostrado ruptura de RSA-PSS ni aceptación de firmas inválidas.
- **Recomendación:** recuperar la pública original desde una fuente
  autenticada y verificar su procedencia/huella antes de registrarla. Si solo
  aparece la privada original, una eventual extracción de su pública requiere
  un procedimiento autorizado aparte. Generar otro par con el mismo nombre
  no sirve, y no deben reemitirse ni sobrescribirse los comprobantes históricos.
  Para verificar no se necesita la privada ni su contraseña.
- **Estado:** **abierto**. No se generaron claves ni se tocaron firmas.

## 9. Análisis de riesgos

| Elemento | Impacto demostrado o límite | Tratamiento |
| --- | --- | --- |
| AUD-01 | Disponibilidad de documentos históricos afectada | Buscar originales exactos; mantener faltantes declarados. |
| AUD-02 | Trazabilidad de versión y descarga afectadas | No inferir versiones; preservar evidencia y excepciones. |
| AUD-03 | Verificación de dos firmas no disponible | Recuperar material público confiable, no cambiar identidad criptográfica. |
| Recuperación actual | Restaura lo incluido, no lo que ya faltaba | Mantener aceptación explícita de gaps; no presentar recuperación histórica completa. |
| DPAPI CurrentUser | No se probó recuperación en otra cuenta/laptop | Plan separado de custodia y ejercicio autorizado; el paquete ordinario excluye secretos. |
| Copias de seguridad | ACL restringida no equivale por sí sola a cifrado | No se comprobó BitLocker ni protección fuera del equipo; cifrar y probar copias externas. |
| Entorno de desarrollo | CA local, HSTS=0 y servidor de desarrollo no equivalen a producción | No son por sí mismos hallazgos explotables en este alcance loopback; diseñar despliegue de producción aparte. |
| Proxy y procesos locales | Loopback no aísla procesos del mismo equipo | Conservar confianza acotada en proxy y sistema; revisar ante cualquier exposición futura. |
| Eventos | No se verificó almacenamiento externo inmutable ni retención | Definir exportación protegida, revisión y alertas según el despliegue. |
| PDF | Fingerprinting no impide copia o eliminación de marca; validación no es antimalware | No publicitar DRM ni protección absoluta del contenido. |
| SSH/VPN | Sesión Ed25519 no repetida y VPN solo propuesta | Pruebas futuras autorizadas; no abrir puertos como parte de esta auditoría. |
| Git | Reglas correctas no demuestran ausencia en historial | Revisar repositorio real antes de publicar; no inicializar ni subir respaldos aquí. |

No se demostraron vulnerabilidades explotables críticas o altas con las pruebas
realizadas. Esto no descarta defectos fuera de los casos ejecutados ni convierte
las comprobaciones pendientes en aprobadas.

## 10. Recomendaciones priorizadas

1. **Prioridad alta de recuperación, no severidad alta de explotación:**
   localizar los originales y la pública histórica desde fuentes confiables.
   Preservar todos los registros mientras se investiga.
2. **Prioridad media:** esclarecer las cuatro líneas sin versión mediante
   evidencia histórica; registrar la limitación cuando no pueda resolverse.
3. **Prioridad media preventiva:** mantener inventario y copias verificadas de
   PDF, versiones y claves públicas; custodiar secretos por separado con un
   plan de recuperación DPAPI probado bajo autorización.
4. **Antes de publicar o desplegar fuera de localhost:** revisar historial Git,
   servidor de producción, TLS, firewall, confianza del proxy, SSH efectivo y
   gestión de eventos. VPN/IPsec requiere otro despliegue y pruebas propias.

No se implementó ninguna remediación durante esta auditoría.

### 10.1 Repetición de las consultas y pruebas

Desde PowerShell en la raíz del proyecto:

```powershell
# Solo lectura sobre el estado real; no carga la privada ni descifra DPAPI.
.\venv\Scripts\python.exe -B docs\evidencias\auditoria\verificar_lectura.py
if ($LASTEXITCODE -ne 0) { throw 'Fallo la verificacion de datos.' }

# Red local, reglas Git en temporal y check Django sin secreto real.
.\venv\Scripts\python.exe -B docs\evidencias\auditoria\comprobar_entorno.py
if ($LASTEXITCODE -ne 0) { throw 'Fallo la verificacion de entorno.' }

# Pruebas sintéticas de recuperación.
.\venv\Scripts\python.exe -B -W error::ResourceWarning `
    -m unittest discover -s scripts -p test_recovery.py -v
if ($LASTEXITCODE -ne 0) { throw 'Fallo la suite de recuperacion.' }
```

Los dos verificadores son evidencia específica de esta ejecución: el primero
fija la ubicación y la huella confiable del paquete ya probado; el segundo
espera Caddy activo y la CA pública local. Si esos recursos cambian o dejan de
estar disponibles, se debe documentar el error, no relajar la validación para
obtener un aprobado. No ejecutan código procedente del respaldo.

Para repetir la suite Django sin configurar secretos reales ni persistir
variables en PowerShell:

```powershell
@'
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix="audit-isolated-") as temporary:
    env = os.environ.copy()
    env.update({
        "DJANGO_DEBUG": "true",
        "DJANGO_LOCAL_HTTPS": "false",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(48),
        "DJANGO_PRIVATE_CATALOG_ROOT": temporary,
        "DJANGO_RECEIPTS_PUBLIC_KEYS_DIR": temporary,
        "DJANGO_RECEIPTS_PRIVATE_KEY_PATH": str(Path(temporary) / "unused.pem"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    result = subprocess.run([
        sys.executable, "-B", "manage.py", "test",
        "accounts", "catalog", "cart", "orders", "receipts", "security", "config",
        "docs.evidencias.auditoria.test_controles_auditoria",
        "--noinput", "--verbosity", "2",
    ], env=env)
    raise SystemExit(result.returncode)
'@ | .\venv\Scripts\python.exe -B -
if ($LASTEXITCODE -ne 0) { throw 'Fallo la suite Django.' }
```

El perfil base de la suite es HTTP de pruebas; los casos HTTPS lo activan de
forma explícita. No confundir esas variables del proceso hijo con un cambio
en la configuración real. Conservar nuevas salidas en un directorio con fecha,
sin sobrescribir las evidencias de esta ejecución.

La comparación de originales usó una línea base privada de sesión, no incluida
en el proyecto. Para repetirla debe capturarse **otra línea base antes de las
pruebas** con `Get-FileHash -Algorithm SHA256`, mantenerla fuera de publicación y
comparar al terminar; no reconstruir una línea base después y afirmar
retroactivamente que nada cambió.

Los comandos de respaldo/restauración real, aislamiento, autorización de
faltantes y custodia de la huella confiable están en
[RESPALDO_RESTAURACION.md](RESPALDO_RESTAURACION.md). No se repitieron sobre el
origen para esta auditoría.

## 11. Conclusión

Los 61 casos automatizados ejecutados aprobaron, y las consultas de solo lectura
confirmaron integridad SQLite (`integrity_check=ok`, `foreign_key_check` sin
filas), tres comprobantes verificables, HTTPS local y revalidación de tres
restauraciones. Se rechazó nuevamente la copia deliberadamente alterada sin
tocar el paquete válido.

Se documentan **tres hallazgos medios abiertos**, todos de disponibilidad,
trazabilidad o recuperación histórica. Las barreras de rechazo funcionan:
no se sustituyen PDF ni se aceptan firmas por falta de material original.
Por ello, la recuperación de los datos disponibles está comprobada, pero
**la disponibilidad y verificación de todo el histórico no están completas**.

La matriz contiene 13 controles aprobados, 3 que no cumplen y 4 verificaciones
pendientes. La VPN no está implementada ni probada. No se afirma una nueva
sesión SSH Ed25519, recuperación DPAPI entre equipos o limpieza del historial Git.

Se crearon únicamente este informe y archivos de evidencia dentro de
[evidencias/auditoria](evidencias/auditoria). La comparación de 22 originales
no detectó cambios, incluida la base activa, configuración, PDF originales,
material RSA existente y DPAPI cifrados. No se modificaron usuarios, roles,
órdenes, pagos, comprobantes históricos, modelos, migraciones, entorno,
Caddy, SSH ni firewall; no se regeneraron secretos ni se subieron respaldos.

Documentación interna complementaria:
[HTTPS local](../config/HTTPS_LOCAL.md),
[VPN/IPsec propuesta](ARQUITECTURA_VPN_IPSEC.md) y
[respaldo/restauración](RESPALDO_RESTAURACION.md). Sus resultados anteriores
se identifican como tales, no como pruebas nuevas de esta auditoría.
