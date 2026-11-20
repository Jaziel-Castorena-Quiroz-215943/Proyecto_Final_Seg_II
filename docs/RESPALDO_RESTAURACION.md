# Respaldo y restauración de la plataforma

**Proyecto:** Plataforma Segura de Venta y Distribución de Contenido Digital.  
**Asignatura:** Seguridad de la Información II.  
**Ejecución real:** 19 de noviembre de 2026, zona horaria UTC-06:00.

> **Resultado:** se respaldó el material disponible y se verificó una restauración
> real en carpetas aisladas, sin alterar los originales. Existen faltantes
> anteriores al respaldo: cuatro PDF distintos ausentes en nueve referencias,
> cuatro líneas de orden sin versión PDF y una clave pública histórica ausente.
> No se declara recuperación completa de las descargas ni de la verificación
> criptográfica histórica. Continuar con esas limitaciones fue autorizado
> expresamente por el responsable del proyecto.

## 1. Objetivo y alcance

Demostrar la recuperación de SQLite y del almacenamiento privado disponible
sin sobrescribir los datos activos, ejecutar migraciones o regenerar secretos.
El procedimiento conserva las filas históricas y sus firmas tal como están.

Se implementaron:

- [backup.ps1](../scripts/backup.ps1): entrada PowerShell para crear respaldos.
- [restore.ps1](../scripts/restore.ps1): restauración exclusivamente aislada.
- [recovery.py](../scripts/recovery.py): implementación compartida de la API
  SQLite, manifiesto, SHA-256, validaciones y permisos.
- [test_recovery.py](../scripts/test_recovery.py): pruebas con datos sintéticos.

El módulo Python evita duplicar validaciones en PowerShell y utiliza el
intérprete del entorno virtual del proyecto, nunca un ejecutable del paquete
recibido. Los scripts funcionan desde cualquier directorio mediante su propia
ubicación. No modifican la aplicación, su configuración ni sus registros.

Se trata de **recuperación de datos**, no de una imagen completa del equipo.
El código fuente confiable, las dependencias, los secretos y los servicios
externos requieren procedimientos separados.

## 2. Inventario y ubicación de los datos

La inspección se basó en [settings.py](../config/settings.py),
[modelos del catálogo](../catalog/models.py),
[modelos de órdenes](../orders/models.py),
[servicio de comprobantes](../receipts/services.py),
[criptografía de comprobantes](../receipts/crypto.py) y
[fingerprinting](../security/fingerprinting.py).

| Elemento | Ubicación y persistencia actuales | Tratamiento |
| --- | --- | --- |
| Base SQLite | `db.sqlite3` en la raíz del proyecto, según la configuración actual | Snapshot consistente mediante `sqlite3.Connection.backup`. Incluye todas las tablas, no solo los conteos de la evidencia. |
| Usuarios, catálogo, carrito, órdenes y pagos | SQLite | Se conservan filas, relaciones, estados y versiones registradas. |
| Comprobantes | Tabla `receipts_receipt`: cuerpo JSON canónico, SHA-256, firma, identificador de clave y relación al pago | No son PDF guardados en disco. No se regeneran ni vuelven a firmar. |
| Originales PDF del catálogo y versiones anteriores aún conservadas | `PRIVATE_CATALOG_ROOT`, actualmente `%USERPROFILE%\DjangoRecuperacion\rsa-demo-2026\catalogo` | Se incluyen los seis PDF disponibles, aunque alguno no esté referenciado actualmente. |
| Referencias históricas PDF | `orders_orderitem.pdf_name` y `pdf_sha256` | Se cotejan contra los archivos disponibles, sin completar valores ausentes ni sustituir versiones. |
| PDF personalizados | Generados en memoria por `watermark_pdf` y enviados como respuesta HTTP | El servidor no conserva automáticamente el binario entregado. No existe un directorio de personalizados que pueda copiarse. |
| Asociaciones de fingerprinting | Tabla `security_downloadfingerprint` | Se conservan token, asociaciones y huella del documento emitido. Esto no equivale a conservar su binario. |
| Claves públicas de comprobantes | `%USERPROFILE%\DjangoRecuperacion\rsa-demo-2026\publicas` | Se incluye el PEM público disponible tras comprobar que es una clave pública RSA. |
| Claves privadas y secretos | Archivos externos referidos por el lanzador y DPAPI | Excluidos del paquete ordinario; recuperación separada en la sección 9. |

El código actual no configura otro almacén persistente de comprobantes o PDF
personalizados. Los archivos descargados que estén únicamente en equipos de
usuarios no forman parte del almacenamiento del servidor inspeccionado.

### 2.1 Faltantes anteriores a esta prueba

La lectura del origen encontró:

- **Cuatro PDF distintos ausentes**, utilizados en **nueve referencias**
  entre productos y líneas de órdenes.
- **Cuatro líneas de orden sin nombre o SHA-256 de versión PDF**.
- **Dos comprobantes con `rsa-2026`**, cuya clave pública no está disponible.
- **Tres comprobantes con `rsa-demo-2026`**, cuya clave pública sí está disponible.

Los seis PDF existentes no presentaron discrepancias en las referencias que
sí podían contrastarse. Los nombres técnicos de archivos ausentes figuran
únicamente en el manifiesto protegido, no se necesitan datos personales para
presentar esta evidencia.

Los scripts rechazan estos faltantes por defecto. `-AllowKnownGaps` autoriza
conservar y restaurar el estado disponible, con limitaciones explícitas; no
ignora un archivo perdido durante la copia ni una huella incorrecta. Una
discrepancia de contenido en un PDF existente siempre produce error.

## 3. Elementos excluidos y justificación

| Exclusión | Justificación |
| --- | --- |
| Clave privada RSA, contraseñas y archivos `.dpapi` | Separación del respaldo de datos y el material necesario para usar secretos. |
| `.env` | Evitar incorporar configuración personal o secretos accidentales; se reconstruye desde el ejemplo y el inventario autorizado. |
| Clave secreta Django | Debe recuperarse por un canal de custodia independiente; no se genera una nueva durante esta fase. |
| Claves privadas y almacén TLS de Caddy, claves SSH | Son identidades de servicios y requieren respaldo restringido separado. |
| Código fuente y scripts ejecutables | Deben obtenerse de una versión confiable; nunca se ejecuta código de un paquete recibido. |
| Entorno virtual, cachés y estáticos recopilados | Se reconstruyen desde código y dependencias confiables. |
| SQLite auxiliares `-wal`, `-shm` y journal | La API de respaldo integra la vista consistente en una base autónoma; no se copian como si fueran una instantánea válida. |
| Copias antiguas de SQLite de la raíz del proyecto | No son la base activa ni constituyen un respaldo coherente del estado actual. |

SQLite contiene información sensible, incluidos hashes de contraseña,
sesiones y asociaciones de usuarios. Excluir secretos externos **no convierte
el paquete en público**. Debe protegerse como dato confidencial.

El respaldo usa una lista estricta: SQLite, nombres PDF UUID generados por el
proyecto y PEM públicos válidos. Archivos inesperados en los directorios
seleccionados provocan error, no una copia indiscriminada que pudiera incluir
una clave privada.

## 4. Almacenamiento y permisos

Los destinos fijos están fuera del proyecto:

```text
%LOCALAPPDATA%\ProyectoFinalRecuperacion\
    respaldos\
    restauraciones\
    pruebas\
```

Los scripts rechazan destinos dentro del proyecto, de los directorios
originales de datos o de un árbol con `.git`. Crean carpetas con herencia
desactivada y acceso únicamente para el usuario de Windows actual y `SYSTEM`.
Si una carpeta de almacenamiento existente tiene permisos incompatibles, se
rechaza; no se cambian silenciosamente sus permisos existentes.

Se rechazan enlaces simbólicos, junctions/puntos de reanálisis y archivos con
enlaces duros en las rutas inspeccionadas. Los datos copiados heredan los
permisos restringidos. En esta prueba se verificaron las ACL reales.

**Las ACL no cifran los archivos**, no protegen frente a administradores con
capacidad de tomar posesión y no sustituyen un respaldo externo.

## 5. Procedimiento de respaldo

### 5.1 Requisitos

- Windows con PowerShell y las herramientas locales `whoami` e `icacls`.
- Python 3.13 del entorno virtual del proyecto.
- Dependencias instaladas desde [requirements.txt](../requirements.txt);
  el módulo utiliza `python-dotenv` y `cryptography`, ya disponibles.
- Configuración no secreta del catálogo y las claves públicas en `.env` o
  variables del proceso; el entorno tiene prioridad.
- Espacio suficiente y lectura de la base y del almacenamiento.

No es necesario descifrar DPAPI ni cargar la clave privada para respaldar datos.
La base activa es explícitamente la de la raíz del proyecto; si cambia su
ubicación en el futuro, debe revisarse este procedimiento.

### 5.2 Ejecución desde PowerShell

Ejemplo desde la raíz del proyecto:

```powershell
# Procedimiento normal: rechaza faltantes.
.\scripts\backup.ps1

# Estado actual: solo tras revisar y autorizar las limitaciones preexistentes.
.\scripts\backup.ps1 -AllowKnownGaps
```

Se obtiene un resumen JSON con carpeta, huella del manifiesto, cantidades y
estado. No se muestran nombres, correos, contenido de documentos ni secretos.
Los errores devuelven un código distinto de cero.

### 5.3 Funcionamiento

1. Crea una carpeta restringida `.partial-backup-...`, con fecha, microsegundos
   y un sufijo aleatorio para evitar colisiones.
2. Abre el SQLite original en modo lectura y establece una transacción de
   lectura; obtiene integridad, relaciones y conteos de esa vista.
3. Usa `Connection.backup` para crear el snapshot. No copia directamente el
   archivo de una base activa. Limita la espera de progreso a 60 segundos.
4. Copia los archivos privados disponibles y las claves públicas validadas.
5. Contrasta las huellas PDF con las referencias del snapshot.
6. Comprueba que no cambió el inventario de archivos durante la copia y que
   se mantienen las huellas de la base original y su WAL, si existe.
7. Escribe `manifest.json`: archivo, tamaño, SHA-256, estado de SQLite,
   conteos y faltantes preexistentes.
8. Crea `COMPLETE` con el SHA-256 del manifiesto y valida todo el paquete.
   Solo después renombra la carpeta a `backup-...`.

Si ocurre un error, no se imprime un resultado exitoso y la carpeta de trabajo
permanece identificada como parcial. No se borra automáticamente para ocultar
la evidencia del fallo. Una restauración rechaza carpetas parciales.

SQLite y el sistema de archivos no comparten una transacción atómica. Se
recomienda una ventana sin escrituras. La API permite respaldar SQLite activo,
pero este procedimiento conservador rechaza cambios concurrentes detectados
en la base o en el inventario para poder demostrar también la invariancia del
origen. No detiene el servicio ni impide por sí mismo que otro usuario escriba.

## 6. Verificación del manifiesto

El paquete válido de esta ejecución es:

```text
%LOCALAPPDATA%\ProyectoFinalRecuperacion\respaldos\
backup-20261119-171612-085624-3e582fd6
```

Su manifiesto está en `manifest.json` y contiene **ocho archivos de datos**:
SQLite, seis PDF privados y una clave pública. `COMPLETE` y el propio
manifiesto son metadatos adicionales.

**SHA-256 del manifiesto emitido y utilizado durante la prueba:**

```text
4d328894e0cefa9a0c81c62996e0578e6924a1d6eabdff42413095cc0b7ff8f5
```

Se debe guardar ese valor por un canal confiable separado. SHA-256 detecta
cambios respecto a un valor confiable; un manifiesto no firmado y su marcador
pueden ser reemplazados juntos. Por eso la restauración exige un SHA-256
esperado externo al paquete. **No debe obtenerse ese valor del mismo paquete
recibido que se desea autenticar.**

El código valida versión y estructura del manifiesto, rutas permitidas,
duplicados, tamaños, huellas, marcador y lista exacta de archivos. Rechaza
rutas absolutas, escapes con `..`, flujos alternativos y archivos adicionales
no declarados. La lista ordinaria no admite ejecutables.

## 7. Procedimiento de restauración aislada

### 7.1 Ejecución

Para repetir con el respaldo válido de esta prueba:

```powershell
$paquete = Join-Path $env:LOCALAPPDATA `
    'ProyectoFinalRecuperacion\respaldos\backup-20261119-171612-085624-3e582fd6'
$huellaConfiable = '4d328894e0cefa9a0c81c62996e0578e6924a1d6eabdff42413095cc0b7ff8f5'

.\scripts\restore.ps1 `
    -BackupPath $paquete `
    -ExpectedManifestSha256 $huellaConfiable `
    -AllowKnownGaps
```

Al omitir `-Name`, se crea un nombre nuevo con fecha y sufijo aleatorio.
También se puede especificar, por ejemplo, `-Name ensayo-aislado-03`, siempre
que no exista. No hay un parámetro para restaurar sobre una ruta arbitraria
ni una opción de sobrescritura.

### 7.2 Garantías y verificaciones

1. Verifica el paquete y el SHA-256 confiable **antes** de crear el destino.
2. Recalcula `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, conteos y
   disponibilidad de PDF según la base del respaldo.
3. Sin `-AllowKnownGaps`, rechaza también los faltantes previamente registrados.
4. Crea una carpeta parcial restringida dentro de `restauraciones`.
5. Copia únicamente archivos permitidos y vuelve a comprobar tamaños y hashes.
6. Valida nuevamente el conjunto restaurado y, solo entonces, lo publica con
   su nombre final.

El SQLite del paquete y el restaurado se inspeccionan en lectura, con carga
de extensiones deshabilitada y `trusted_schema=OFF`. No se ejecutan scripts SQL
recibidos, migraciones, módulos Python, aplicaciones ni servidores del paquete.
Solo se usa el código confiable del proyecto y consultas de validación.

La estructura restaurada contiene `db.sqlite3`, `catalog`, `public_keys`,
`manifest.json` y `COMPLETE`. Las rutas de configuración del origen se usan
para prevenir solapamientos, no para escribir en ellas; la restauración no
necesita que los directorios originales aún existan.

## 8. Evidencias y resultados reales

### 8.1 Fechas y ubicaciones

- Snapshot identificado a las **17:16:12**, UTC-06:00.
- Manifiesto fechado **2026-11-19T23:16:12.719971+00:00**, en UTC.
- Comparación y pruebas negativas registradas a las
  **2026-11-19T17:17:40.193629-06:00**.
- Restauraciones independientes: `restauraciones\prueba-real-01` y
  `restauraciones\prueba-real-02`.
- Validación final adicional: `restauraciones\prueba-sin-fuentes-03`, usando
  rutas de origen inexistentes solo en las variables del proceso de prueba,
  sin eliminar archivos ni modificar `.env`.
- Evidencia JSON no secreta:
  `%LOCALAPPDATA%\ProyectoFinalRecuperacion\pruebas\resultados-20261119.json`.

### 8.2 Cantidades comprobadas

| Elemento | Original | Restauración 01 | Restauración 02 |
| --- | ---: | ---: | ---: |
| Usuarios | 3 | 3 | 3 |
| Productos | 6 | 6 | 6 |
| Órdenes | 8 | 8 | 8 |
| Pagos simulados | 7 | 7 | 7 |
| Comprobantes | 5 | 5 | 5 |
| Registros de fingerprinting | 4 | 4 | 4 |
| PDF privados disponibles | 6 | 6 | 6 |
| Claves públicas disponibles | 1 | 1 | 1 |

Se compararon además el esquema y **todas las filas de las 20 tablas** entre
el original y la restauración 01: coincidieron. Las restauraciones 01 y 02
verificaron los mismos hashes del snapshot y todos los archivos del manifiesto.

### 8.3 Verificaciones

| Verificación ejecutada | Resultado |
| --- | --- |
| `PRAGMA integrity_check` en origen, snapshot y restauraciones | `ok`. |
| `PRAGMA foreign_key_check` | Sin filas: no se detectaron violaciones. |
| SHA-256 de los ocho archivos incluidos | Coincidente antes y después de restaurar. |
| SHA-256 del manifiesto | Coincide con el valor confiable registrado en esta guía. |
| Permisos de almacenamiento y SQLite restaurado | Acceso restringido al usuario actual y `SYSTEM`. |
| Comprobantes restaurados con clave pública disponible | Tres firmas RSA-PSS/SHA-256 verificadas con el código criptográfico confiable del proyecto, sin crear registros. |
| Comprobantes con clave `rsa-2026` ausente | Dos pendientes de verificación criptográfica; sus filas y firmas se conservaron. |
| Repetición en carpeta nueva | Aprobada mediante restauración 02. |
| Restauración sin directorios fuente disponibles | Aprobada mediante restauración 03; mismos conteos, huellas e integridad, sin tocar los originales. |
| Reutilización de destino existente | Rechazada, sin sobrescribir la restauración 01. |
| Restauración sin autorizar faltantes | Rechazada. |
| Copia real deliberadamente alterada | Rechazada antes de crear una restauración final. |
| Respaldo válido después de la prueba de alteración | Verificado nuevamente y sin cambios. |
| Huellas de 17 archivos originales controlados | Sin cambios: base, configuración, PDF, claves existentes y DPAPI cifrados. No se reveló su contenido. |

La base original conservó el SHA-256:

```text
badd680f6d4816493ab7d10c466be01eafb133a60fbdd3c509d582f547957e89
```

El snapshot y cada SQLite restaurado coinciden con la huella registrada en el
manifiesto:

```text
31eefe196cde6a802c2bac623556581c3916aff1db4ced6f424142d6c24dc92a
```

Estas dos huellas no tienen por qué ser iguales entre sí: la API crea otra
base SQLite y puede cambiar metadatos internos. La equivalencia de datos se
demostró comparando esquema y filas, no suponiendo igualdad física con el origen.
El modo de journal observado en el original fue `delete`.

### 8.4 Prueba de alteración, sin afectar el paquete válido

Se creó una copia en el directorio restringido:

```text
%LOCALAPPDATA%\ProyectoFinalRecuperacion\pruebas\copia-alterada-20261119-1718
```

Se añadieron bytes a **un PDF de esa copia**, conservando el manifiesto
original. Se invocó el restaurador con la huella confiable; devolvió error
por archivo ausente o alterado y no creó `restauraciones\rechazo-alterado`.
Después se validó nuevamente el respaldo válido.

No se eliminó ni alteró ningún original para simular una recuperación.
La copia alterada permanece identificada como evidencia negativa y no debe
usarse para restaurar.

### 8.5 Pruebas automatizadas y fallos corregidos

Comando ejecutado:

```powershell
.\venv\Scripts\python.exe -B -W error::ResourceWarning `
    -m unittest discover -s scripts -p test_recovery.py -v
```

**Resultado final: cinco pruebas aprobadas**, con casos para restauración
repetible, rechazo de cambios, archivos omitidos/adicionales, marcador
incompleto, rutas inseguras, huella de manifiesto incorrecta, autorización de
faltantes y claves foráneas inválidas.

La primera ejecución encontró conexiones SQLite de los datos sintéticos de
prueba sin cierre explícito, lo que impidió limpiar algunos temporales en
Windows. Se corrigieron los fixtures y se repitió la suite satisfactoriamente.
Ese fallo no afectó la base original. Los rechazos deliberados son controles
aprobados, no restauraciones exitosas del paquete alterado.

## 9. Recuperación separada de secretos y del entorno

Para recuperar el servicio completo, además del paquete de datos se necesita:

1. Código y migraciones de una versión confiable de la plataforma; Python
   3.13, Django 6.1.3 y las dependencias fijadas en `requirements.txt`,
   especialmente `cryptography`, PyMuPDF y los algoritmos de contraseña usados.
2. Caddy y una configuración HTTPS autorizada. Su almacén TLS y clave privada
   de CA se gestionan por separado; no se incluyen en este paquete ordinario.
3. El mismo `DJANGO_SECRET_KEY` cuando se requiera preservar la validez de
   sesiones y otros datos firmados con esa clave.
4. La clave RSA privada cifrada y su contraseña para emitir comprobantes
   nuevos. Para verificar comprobantes anteriores se necesitan las claves
   **públicas originales correspondientes**, no la privada.
5. Credenciales y claves SSH, permisos NTFS y configuración de servicios
   recuperados mediante procedimientos administrativos separados.

Actualmente `django-secret.dpapi` y `rsa-demo-2026\password.dpapi` contienen
secretos protegidos mediante DPAPI CurrentUser. Copiar solamente esos archivos
a otra laptop, o crear una cuenta con el mismo nombre, no garantiza poder
descifrarlos: intervienen el perfil, las claves maestras DPAPI y las condiciones
de recuperación de Windows.

Se recomienda custodiar por separado una recuperación autorizada de los
secretos en un gestor o bóveda cifrada, con acceso mínimo, respaldo y prueba de
recuperación. El material privado RSA cifrado también necesita custodia
independiente. No registrar contraseñas en consola, documentación, manifiestos
o archivos públicos; no confiar únicamente en conservar un blob DPAPI.

Para una validación futura de la aplicación completa se debe preparar una
copia confiable de código en otro directorio, configurar allí la base
restaurada y el catálogo restaurado, y recuperar los secretos por ese canal
separado. No iniciar el lanzador original apuntando accidentalmente al entorno
activo ni sustituir su `.env`. Esta prueba de datos no ejecutó la aplicación
restaurada ni ensayó la recuperación de secretos en otro equipo.

## 10. Cómo repetir y ampliar la prueba

1. Revisar faltantes y reservar una ventana sin escrituras concurrentes.
2. Ejecutar las pruebas automatizadas anteriores.
3. Ejecutar `backup.ps1`; autorizar `-AllowKnownGaps` únicamente si se
   documentan y aceptan los faltantes actuales.
4. Guardar la ruta y el SHA-256 emitido del manifiesto en un registro confiable
   separado del paquete.
5. Ejecutar `restore.ps1` dos veces sin `-Name` o con nombres distintos.
6. Comparar conteos, integridad, relaciones y SHA-256; registrar fecha y estado.
7. Para probar alteración, crear **otra copia** del paquete dentro de un
   directorio restringido, modificar un archivo de esa copia y utilizar la
   huella original. Debe rechazarse. No tocar el paquete válido ni los datos
   activos.
8. Intentar reutilizar un nombre de restauración para comprobar su rechazo.
9. Volver a verificar los originales y conservar la evidencia sin información
   personal. Nunca declarar éxito si un comando terminó con error.

Una modificación válida del estado de producción posterior a un respaldo no
es una corrupción del respaldo: representa otro punto de recuperación y debe
documentarse como tal.

## 11. Riesgos, límites y recomendaciones

- **Faltantes históricos:** el procedimiento conserva el estado, no recupera
  PDF o claves públicas que ya no están. No se sustituyen archivos con
  contenido nuevo ni se reescriben comprobantes.
- **Personalizados ya entregados:** los registros se recuperaron, pero los
  binarios exactos de descargas anteriores no estaban almacenados. Una nueva
  emisión no garantiza reconstruir el mismo archivo ni su huella previa.
- **Secretos separados:** emisión de comprobantes y servicio completo quedan
  condicionados a recuperar el material secreto autorizado.
- **Consistencia entre recursos:** SQLite tiene snapshot consistente;
  DB y archivos no tienen una transacción conjunta. Las verificaciones
  conservadoras detectan cambios observados, no sustituyen una política de
  mantenimiento y versiones inmutables.
- **Confidencialidad:** ACL restringidas no son cifrado. Usar almacenamiento
  cifrado, respaldo fuera del equipo y control de dispositivos extraíbles;
  no subir paquetes a GitHub.
- **Autenticidad:** custodiar el hash confiable aparte. Si un atacante cambia
  a la vez el paquete y el registro confiable, SHA-256 por sí solo no lo evita.
- **Protección contra ransomware y fallos físicos:** aplicar una estrategia
  3-2-1, incluir copia fuera de línea/inmutable y verificar restauraciones
  periódicamente. No se ejecutó una transferencia externa en esta fase.
- **Retención:** definir responsables, plazos, control de acceso, capacidad
  y eliminación autorizada. Los scripts no borran respaldos ni originales.
- **Integridad no equivale a seguridad del contenido:** los PDF se copian
  como datos; no se certifica ausencia de contenido activo o malware.
- **Alcance de las pruebas:** se verificó restauración de datos en esta
  laptop, no recuperación bare-metal, otro usuario Windows, otra laptop,
  Caddy/SSH completos ni un objetivo formal de RTO/RPO.

**Cierre de fase:** la restauración aislada del material disponible está
ejecutada y verificada. La recuperabilidad total de los archivos históricos,
de los dos comprobantes sin clave pública y del entorno completo permanece
condicionada a resolver los pendientes expresamente identificados.
