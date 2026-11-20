# Plataforma Segura de Venta y Distribución de Contenido Digital

Proyecto académico de Seguridad de la Información II: aplicación Django para
publicar PDF privados, comprarlos mediante pagos **simulados**, emitir comprobantes
JSON firmados y descargar copias personalizadas con fingerprinting.
No procesa pagos bancarios ni emite facturas fiscales.

## Funcionalidades

- Registro, autenticación, perfil y recuperación de contraseña.
- Catálogo público de productos publicados y gestión restringida a OPERADOR.
- Carrito, cotización firmada con expiración, órdenes e idempotencia de pagos.
- Firma RSA-PSS/SHA-256 y comprobación de integridad y relación con la compra.
- Descargas privadas por propietario y versión exacta de PDF.
- Fingerprinting seudónimo y extracción restringida a superusuario.
- Eventos de seguridad, HTTPS local con Caddy y arranque con secretos DPAPI.
- Respaldo consistente SQLite y restauración en carpetas aisladas.

## Roles

| Perfil | Funciones |
| --- | --- |
| Visitante | Consultar productos publicados, registrarse e iniciar sesión. |
| CLIENTE | Gestionar su carrito, comprar, simular pagos y acceder a sus órdenes, comprobantes y descargas autorizadas. |
| OPERADOR | Crear/editar/publicar/archivar productos; consultar órdenes y comprobar comprobantes de todos los clientes, sin pagar ni descargar en su nombre. |
| ADMINISTRADOR | Etiqueta de negocio; no concede privilegios de Django automáticamente. |
| Superusuario activo | Administrar cuentas/roles y consultar eventos; extraer fingerprints. Necesita además acceso al sitio admin (`is_staff`). No recibe acceso implícito al catálogo de operador ni a compras. |

El registro público siempre crea CLIENTE. No hay un panel genérico que convierta
el rol ADMINISTRADOR en superusuario.

## Tecnologías

Entorno documentado: Windows, Python **3.13.7**, Django **6.1.3**, SQLite,
`argon2-cffi`, `cryptography`, PyMuPDF, `python-dotenv`, PowerShell,
Caddy 2 y OpenSSH para Windows con Ed25519. Las versiones Python/Django son
las observadas localmente; las dependencias están fijadas en
[requirements.txt](requirements.txt). No se certificó aquí una instalación
limpia desde un índice de paquetes.

## Estructura

| Ruta | Responsabilidad |
| --- | --- |
| [config](config) | Configuración Django, rutas y perfil HTTPS local. |
| [accounts](accounts) | Usuario, roles, autenticación y eventos. |
| [catalog](catalog) | Metadatos de productos y almacenamiento privado. |
| [cart](cart) / [orders](orders) | Carrito, cotización, órdenes y pagos simulados. |
| [receipts](receipts) | Comprobantes JSON, firma y verificación RSA. |
| [security](security) | Personalización de PDF y extracción de fingerprints. |
| [scripts](scripts) | Respaldo, restauración y sus pruebas sintéticas. |
| [docs](docs) | Guías finales, informes y evidencias agregadas. |
| [Iniciar-Seguro.ps1](Iniciar-Seguro.ps1) | Carga de configuración y secretos DPAPI; validación y arranque Django. |
| [Caddyfile](Caddyfile) | TLS local, redirección y proxy en loopback. |
| [.env.example](.env.example) | Plantilla sin valores secretos y con rutas ilustrativas. |

SQLite se ubica en la raíz y está excluida de Git. Los PDF y las claves privadas
se mantienen fuera del proyecto; no son archivos estáticos públicos.

## Inicio

**Instalación nueva y vacía:** seguir [INSTALACION](docs/INSTALACION.md).
No aplicar esos pasos de inicialización a la base existente.

**Equipo ya preparado**, desde la raíz:

```powershell
.\Iniciar-Seguro.ps1 -Check
.\Iniciar-Seguro.ps1
```

El primer comando descifra los secretos con el usuario Windows actual y prueba
la firma sin crear registros; no inicia un servidor. El segundo inicia Django
en `127.0.0.1:8000`. Caddy se inicia por separado según
[HTTPS_PKI](docs/HTTPS_PKI.md). Navegar a `https://localhost:8443` únicamente
con la confianza del certificado validada.

El lanzador también puede invocarse mediante su ruta absoluta desde otra carpeta.
No ejecuta migraciones ni inicia Caddy. DPAPI CurrentUser **no es portable
automáticamente** a otro usuario o computadora.

## Índice de documentación

1. [Instalación desde cero en Windows](docs/INSTALACION.md).
2. [Arquitectura del sistema y flujos](docs/ARQUITECTURA_SISTEMA.md).
3. [Seguridad criptográfica y acceso](docs/SEGURIDAD_CRIPTOGRAFICA.md).
4. [HTTPS y PKI local](docs/HTTPS_PKI.md).
5. [SSH y autenticación Ed25519](docs/SSH.md).
6. [Manual de usuario por rol](docs/MANUAL_USUARIO.md).
7. [Pruebas y evidencias existentes](docs/PRUEBAS_EVIDENCIAS.md).
8. [VPN/IPsec: arquitectura propuesta, no implementada](docs/ARQUITECTURA_VPN_IPSEC.md).
9. [Respaldo y restauración: procedimiento y pruebas reales](docs/RESPALDO_RESTAURACION.md).
10. [Auditoría: resultados y hallazgos históricos](docs/AUDITORIA_SEGURIDAD.md).

Los README de [cuentas](accounts/README.md), [catálogo](catalog/README.md),
[órdenes](orders/README.md), [comprobantes](receipts/README.md) y
[fingerprinting](security/README.md) amplían detalles de implementación.

## Estado y límites

La evidencia del **19/11/2026** registra 56 pruebas Django y cinco de recuperación
aprobadas. La matriz de auditoría contiene 13 controles aprobados, tres no
conformes por limitaciones históricas y cuatro pendientes; no son 20 pruebas
automatizadas adicionales.

| Hallazgo histórico abierto | Impacto confirmado |
| --- | --- |
| AUD-01 | Cuatro PDF distintos ausentes en nueve referencias; cuatro líneas pagadas afectadas. |
| AUD-02 | Cuatro líneas sin versión de PDF registrada, tres pagadas. |
| AUD-03 | Dos comprobantes no verificables con el material disponible por falta de la pública `rsa-2026`; otros tres sí se verificaron. |

Son limitaciones de disponibilidad, trazabilidad y recuperación, **no
vulnerabilidades explotables demostradas**. Los registros históricos se conservan
y el sistema rechaza los casos sin material verificable.

HTTPS y SSH actuales están limitados a loopback. VPN/IPsec es una propuesta.
La CA local, HSTS desactivado y `runserver` no constituyen un despliegue público
de producción. Fingerprinting no es DRM ni una marca resistente a eliminación.

## Antes de publicar en GitHub

- Se preparó un repositorio local en esta carpeta, rama `main`, sin commits ni
  remotos. La auditoría anterior se realizó antes de inicializarlo; su evidencia
  permanece como fotografía histórica, no como descripción del estado Git actual.
- Revisar [.gitignore](.gitignore), archivos que se vayan a añadir e historial
  si se importa otro repositorio. Reglas de exclusión no eliminan datos ya seguidos.
- Excluir `.env`, bases SQLite, PDF privados, copias de seguridad, DPAPI,
  privadas RSA/SSH/TLS, almacén de Caddy, entornos virtuales y estáticos generados.
  Los respaldos deben permanecer fuera del árbol Git.
- Revisar evidencias y rutas locales para retirar datos personales. No publicar
  cuerpos privados de comprobantes ni archivos de recuperación.
- No ignorar todas las públicas PEM: se pueden distribuir tras comprobar su
  procedencia e integridad y decidir cuáles corresponden al proyecto.
- Decidir licencia y derechos de distribución de código, dependencias y PDF;
  no se ha añadido una licencia ni cargado contenido.
- Probar una instalación limpia, disponibilidad de dependencias y un conjunto de
  demostración independiente antes de afirmar reproducibilidad completa.
- Declarar los tres hallazgos y pendientes sin modificar el histórico para
  ocultarlos. Publicar código no exige exponer el servicio a Internet.

### Inventarios de revisión

La preparación de Git incluye
[archivos publicables](docs/evidencias/prepublicacion/archivos_publicables.csv),
[elementos excluidos](docs/evidencias/prepublicacion/elementos_excluidos.csv) y
[resultados de validación](docs/evidencias/prepublicacion/validaciones.json).
Las evidencias operativas conservadas son agregadas y no incluyen identidades,
documentos privados o secretos. No hay claves públicas PEM copiadas
automáticamente desde el almacenamiento externo.

Los [atributos Git](.gitattributes) permiten los saltos Markdown y las líneas
finales de los logs capturados al comprobar espacios. No convierten finales de
línea ni modifican las evidencias originales.

La política permite añadir individualmente públicas de verificación revisadas
en `claves_publicas` o `publicas`, sin permitir por ello todas las PEM del proyecto.
Antes de añadir una, comprobar su procedencia y que contiene solo material
público. Las claves de SSH y TLS no son las de comprobantes.

La instalación nueva genera sus propios blobs DPAPI binarios y su pareja RSA;
no necesita los DPAPI del autor. Los verificadores de auditoría histórica sí
dependen del paquete local previamente documentado, por lo que no son un
requisito de instalación ni una prueba genérica para otro equipo.

### Comandos posteriores, solo tras autorización

No se ejecutaron commit, configuración de remoto ni publicación. Desde la raíz,
revisar primero los inventarios y cualquier cambio posterior. Configurar una
identidad pública propia; los siguientes valores son ilustrativos:

```powershell
git --no-pager status --short
git config --local user.name "NOMBRE_PUBLICO"
git config --local user.email "USUARIO@users.noreply.github.com"
git add -- .gitignore .gitattributes .env.example README.md requirements.txt manage.py `
    Caddyfile Iniciar-Seguro.ps1 accounts cart catalog config docs orders receipts scripts security
git --no-pager diff --cached --stat
git --no-pager diff --cached --check
git --no-pager diff --cached --name-only
```

Revisar el contenido preparado en un editor seguro sin compartir valores
sensibles. Si aparece algo inesperado, detenerse antes del commit. Las reglas
de exclusión no protegen archivos ya rastreados.

```powershell
git commit -m "Entrega final del proyecto de Seguridad de la Informacion II" `
    -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

Después de ese primer commit, y únicamente con autorización de publicación,
crear un repositorio GitHub vacío sin archivos iniciales. Sustituir `USUARIO`
y `REPOSITORIO` por los valores elegidos, sin incrustar credenciales en la URL:

```powershell
git remote add origin https://github.com/USUARIO/REPOSITORIO.git
git push -u origin main
```

Autenticarse mediante el mecanismo seguro de Git/GitHub, no mediante tokens
guardados en comandos o archivos. Si el remoto existe o contiene commits,
revisar el caso antes de continuar; no usar `--force` ni sobrescribir historial.
