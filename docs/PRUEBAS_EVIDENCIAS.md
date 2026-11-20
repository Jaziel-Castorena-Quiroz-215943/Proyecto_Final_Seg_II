# Pruebas y evidencias

[Índice general](../README.md) · [Informe de auditoría](AUDITORIA_SEGURIDAD.md)

## 1. Alcance y fecha

Este documento organiza **evidencia ya existente del 19/11/2026**.
No se ejecutaron nuevamente pruebas funcionales, restauraciones, sesiones SSH,
inicialización de bases o generación de claves al redactarlo.
Los controles de esta edición documental se limitan a enlaces, consistencia,
sintaxis de ejemplos y preservación de archivos no Markdown.

No hay capturas inventadas ni demostración de una VPN operativa.
Una prueba esperada o propuesta no se cuenta como aprobada.

## 2. Resultados automatizados existentes

| Suite | Resultado registrado | Evidencia |
| --- | --- | --- |
| Django: cuentas, catálogo, carrito, órdenes, comprobantes, fingerprinting, configuración y tres casos complementarios | 56 pruebas aprobadas; código de salida 0; SQLite de pruebas en memoria. | [Log final Django](evidencias/auditoria/tests_django_final.txt) |
| Recuperación con fixtures sintéticos | Cinco pruebas aprobadas, incluidas repetición, alteración, rutas/manifiesto y relaciones inválidas. | [Log de recuperación](evidencias/auditoria/tests_recuperacion.txt) |

**Total: 61 casos automatizados aprobados.** Las migraciones visibles en el log
Django corresponden a su base temporal, no a la base activa.
El [primer log Django](evidencias/auditoria/tests_django.txt) se conserva como
antecedente de una incidencia de impresión/codificación; para el resultado
definitivo usar el log final, no atribuir un fallo funcional a esa incidencia.

## 3. Matriz resumida

La [matriz CSV completa](evidencias/auditoria/matriz_pruebas.csv) contiene 20
controles con procedimiento, esperado, obtenido, estado y evidencia.
No equivale a otras 20 pruebas automatizadas.

| Casos | Control | Resultado real | Estado |
| --- | --- | --- | --- |
| AUD-T01–T02 | Autenticación administrativa y separación de roles | Anónimos remitidos a login; sin elevación implícita por rol. | Aprobados |
| AUD-T03–T04 | Descargas y órdenes ajenas | Propietario/pago/rol, aislamiento, precios e idempotencia verificados con fixtures. | Aprobados |
| AUD-T05 | CSRF y sesión | Negativos rechazados; cookie Secure, HttpOnly y SameSite=Lax. | Aprobado |
| AUD-T06 | HTTPS, DEBUG y cabeceras | TLS 1.3 y 308 reales; CA no confiable rechazada; cabeceras y cookies con cliente Django. | Aprobado |
| AUD-T07–T08 | Firmas y PDF manipulados | Tres comprobantes reales válidos y casos sintéticos alterados rechazados. | Aprobados, alcance disponible |
| AUD-T09 | Eventos | Casos automatizados y trece tipos reales consultados en lectura. | Aprobado |
| AUD-T10 | Secretos y exclusiones | Trece reglas Git en repositorio temporal; comprobación acotada de archivos de entorno y texto. | Aprobado, no cubre historial |
| AUD-T11 | Recuperación de lo incluido | Ocho archivos y tres restauraciones existentes revalidados; copia alterada rechazada. | Aprobado con faltantes declarados |
| AUD-T12 | PDF históricos | Cuatro PDF distintos ausentes en nueve referencias; cuatro líneas pagadas afectadas. | No cumple: AUD-01 |
| AUD-T13 | Versionado histórico | Cuatro líneas sin versión, tres pagadas; rechazo seguro. | No cumple: AUD-02 |
| AUD-T14 | Verificación histórica completa | Dos comprobantes sin pública `rsa-2026`; no se aceptan como válidos por omisión. | No cumple: AUD-03 |
| AUD-T15 | SSH y sockets | Configuración leída y puertos 22/8000/8080/8443 solo en loopback. | Aprobado en lectura |
| AUD-T16 | Nueva sesión Ed25519 | No ejecutada; algoritmo reportado por el equipo, archivo autorizado protegido no leído. | Pendiente |
| AUD-T17 | Historial Git | No existía un repositorio activo que inspeccionar. | Pendiente |
| AUD-T18 | DPAPI en otro usuario/equipo | No descifrado ni migrado en la auditoría. | Pendiente |
| AUD-T19 | VPN/IPsec funcional | Solo arquitectura propuesta; sin instalación o túnel probado. | Pendiente, futuro |
| AUD-T20 | Originales | 22 originales controlados conservaron sus SHA-256 al cierre de la auditoría. | Aprobado |

Balance: **13 controles aprobados, tres no conformes y cuatro pendientes**.
Los tres hallazgos son limitaciones de disponibilidad, trazabilidad y
recuperación, no vulnerabilidades explotables demostradas.
Los rechazos deliberados de documentos/respaldos manipulados son controles
correctos, no pruebas fallidas.

## 4. Localización de evidencia

Todas las rutas enlazadas siguientes son relativas a este documento:

| Archivo | Alcance |
| --- | --- |
| [estado_datos.json](evidencias/auditoria/estado_datos.json) | Conteos agregados, integridad, impacto histórico, tres firmas verificadas y tres restauraciones. |
| [estado_entorno.json](evidencias/auditoria/estado_entorno.json) | Perfil configurado, TLS, redirección, SSH, sockets y reglas Git. |
| [invariancia_originales.json](evidencias/auditoria/invariancia_originales.json) | Comparación de 22 originales de la auditoría, no una captura nueva de esta edición documental. |
| [test_controles_auditoria.py](evidencias/auditoria/test_controles_auditoria.py) | Tres pruebas complementarias con identidades sintéticas. |
| [verificar_lectura.py](evidencias/auditoria/verificar_lectura.py) | Consultas reales en lectura y revalidación de paquetes concretos existentes. |
| [comprobar_entorno.py](evidencias/auditoria/comprobar_entorno.py) | Reglas Git en temporal, configuración, loopback y TLS local. |
| [test_recovery.py](../scripts/test_recovery.py) | Pruebas sintéticas del respaldo/restauración. |

La auditoría observó 3 usuarios, 6 productos, 8 órdenes, 7 pagos, 5 comprobantes
y 4 fingerprints; no se publican identidades ni contenido privado.
`integrity_check` devolvió `ok` y `foreign_key_check` no devolvió filas.
Estos datos son una fotografía fechada, no una promesa de conteos permanentes.

Los archivos de respaldo reales permanecen **fuera del proyecto**, bajo el
directorio restringido descrito en
[RESPALDO_RESTAURACION](RESPALDO_RESTAURACION.md).
Esa guía contiene la identificación del paquete y la huella confiable del
manifiesto, las tres restauraciones reales previas y su evidencia externa.
No se copian al repositorio ni se publican los PDF o bases para «demostrar» la prueba.

## 5. Repetir en un entorno aislado

El [informe de auditoría](AUDITORIA_SEGURIDAD.md), sección de repetición, incluye
el bloque PowerShell/Python completo que prepara variables efímeras, catálogo y
claves temporales para `manage.py test`. Usar ese procedimiento, no el lanzador
real ni una base de producción como destino de pruebas.

Para repetir solo los fixtures de recuperación:

```powershell
.\venv\Scripts\python.exe -B -W error::ResourceWarning `
    -m unittest discover -s scripts -p test_recovery.py -v
if ($LASTEXITCODE -ne 0) { throw 'Fallo la suite de recuperacion.' }
```

Los verificadores de auditoría no son pruebas genéricas para una instalación
vacía: fijan rutas/identificación del paquete histórico y su hash confiable,
o requieren Caddy y la CA correctos. Si faltan esos recursos, documentar la
limitación; no editar la evidencia anterior para convertir el error en éxito.

Las pruebas nuevas de certificados se describen en [HTTPS_PKI](HTTPS_PKI.md);
las sesiones SSH propuestas en [SSH](SSH.md); las futuras VPN en
[ARQUITECTURA_VPN_IPSEC](ARQUITECTURA_VPN_IPSEC.md).

## 6. Custodia y preparación para GitHub

Conservar salidas nuevas en una ubicación distinta con fecha y registrar su
alcance, comando y resultado. No sobrescribir logs anteriores. No adjuntar
cookies, tokens de reset, contraseñas, privadas, DPAPI, identidades reales,
PDF privados ni JSON de comprobantes con datos personales.
Una línea base debe capturarse antes del ensayo; no reconstruirla después y
afirmar retroactivamente invariancia.

Las reglas de Git se probaron, pero no se revisaron archivos seguidos ni
historial por falta de repositorio activo. El [README](../README.md) contiene
el checklist pendiente de publicación. La evidencia de recuperación de datos
no acredita recuperación DPAPI entre computadoras ni un despliegue productivo.
