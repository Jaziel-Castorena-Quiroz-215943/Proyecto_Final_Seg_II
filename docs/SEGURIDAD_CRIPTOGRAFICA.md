# Seguridad criptográfica y control de acceso

[Índice general](../README.md) · [Arquitectura](ARQUITECTURA_SISTEMA.md)

## 1. Contraseñas y sesiones

[La configuración](../config/settings.py) prioriza
`Argon2PasswordHasher`, suministrado por `argon2-cffi`, para contraseñas nuevas;
la implementación utilizada emplea Argon2id con sal. También conserva
verificadores PBKDF2, bcrypt-SHA256 y scrypt para compatibilidad. Un hash de
contraseña no es cifrado reversible y no debe reutilizarse como clave RSA.

Se usan los validadores de similitud con el usuario, longitud mínima,
contraseñas comunes y valores enteramente numéricos. El registro no permite
escoger privilegios y crea CLIENTE. La recuperación tiene respuesta uniforme,
token de un uso y caducidad de una hora; el correo actual se entrega a consola,
no a un proveedor real.

En HTTPS, las cookies de sesión son Secure, HttpOnly y SameSite=Lax. CSRF se
comprueba en operaciones modificadoras. No se ha implementado MFA, CAPTCHA
ni limitación de intentos en este módulo; no afirmar resistencia a fuerza bruta.

## 2. Firma de comprobantes

[crypto.py](../receipts/crypto.py) implementa:

| Elemento | Formato |
| --- | --- |
| Documento | JSON con `body`, `sha256` y `signature`; formato `receipt-v1`. |
| Serialización | UTF-8 con claves ordenadas, sin espacios separadores, `ensure_ascii=False` y `allow_nan=False`. |
| Resumen | SHA-256 del cuerpo canónico. |
| Firma | RSA-PSS con SHA-256, MGF1-SHA256 y sal de longitud del digest: 32 bytes. |
| Transporte | Firma en Base64; no es cifrado del contenido. |
| Clave | RSA de al menos 2048 bits; la pública actual documentada tiene 3072. |

La firma se calcula sobre los bytes canónicos del cuerpo, no sobre un JSON
arbitrariamente reindentado ni sobre el texto hexadecimal del resumen.
El cuerpo incluye algoritmo, identificador de clave y datos históricos de la
operación. La verificación comprueba estructura, SHA-256 y firma con la pública
confiable; [el servicio](../receipts/services.py) también contrasta la orden,
el pago y las líneas. Una firma válida no convierte un pago simulado en real.

La cotización del carrito utiliza firma de Django y la clave del proyecto,
no la privada RSA del comprobante. TLS y SSH también tienen claves independientes.

## 3. Custodia y rotación

- Privada RSA en PEM cifrado y fuera del proyecto/webroot, protegida por ACL.
- Contraseña de la privada y `DJANGO_SECRET_KEY` fuera de `.env`; el lanzador
  las obtiene de blobs DPAPI CurrentUser cuyo texto original está en UTF-8.
  No son archivos exportados con `ConvertFrom-SecureString`.
- Directorio de públicas con escritura restringida: su contenido es un ancla
  de confianza, aunque no sea confidencial.
- Identificadores de clave ASCII de 1–64 caracteres, con letras, números,
  guion o guion bajo; pública nombrada `<identificador>.pem`.
- Antes de firmar se comprueba que la pública y la privada correspondan.
- Rotar significa crear un par con **otro identificador** y conservar las
  públicas antiguas. No sobrescribir una pública histórica ni reemitir
  comprobantes como si fueran originales.

DPAPI CurrentUser vincula el secreto al contexto Windows que lo protegió.
Copiar el blob o recrear una cuenta con el mismo nombre no garantiza
descifrarlo en otro equipo. La recuperación requiere una estrategia autorizada
de perfil/DPAPI o custodia alternativa protegida; no se ha probado aquí.
La copia ordinaria de datos excluye privadas, contraseñas y DPAPI:
[procedimiento de recuperación](RESPALDO_RESTAURACION.md).

No existe una PKI de comprobantes con servicio de revocación automático.
Ante compromiso se requiere respuesta operativa: retirar la clave de emisión,
investigar alcance y conservar evidencia y material público con su estado.
No atribuir a las firmas existentes una fecha confiable de sellado de tiempo
externo ni una validación de revocación que la aplicación no implementa.

## 4. Fingerprinting e integridad de PDF

[fingerprinting.py](../security/fingerprinting.py) verifica nombre y SHA-256 de
la versión registrada en la línea. Después genera una copia en memoria con
un identificador aleatorio de 128 bits, visible en cada página e incrustado.
SQLite conserva asociación con usuario/línea y SHA-256 exacto de esa emisión;
no se introducen nombres o correos del comprador en la marca.
Los datos que ya estuvieran en el PDF original no se eliminan automáticamente.

La extracción exige superusuario y coincidencia del identificador y de todos
los bytes mediante su hash. Copiar una marca a otro PDF no lo convierte en
la emisión registrada. Borrarla, imprimir, capturar o reescribir el archivo
puede impedir la identificación: **no es DRM ni una huella robusta a alteración**.

El original admite hasta 20 MiB y debe pasar validación estructural. La copia
personalizada y el documento de extracción admiten hasta 30 MiB. No se personalizan
PDF con indicadores/campos de firma, para evitar invalidarlos. Esto no es un
antivirus ni una validación criptográfica general de firmas PDF.

## 5. Autorización y eventos

| Operación | Restricción |
| --- | --- |
| Gestión de catálogo | OPERADOR activo; sin privilegio implícito para superusuario de otro rol. |
| Compra/pago | CLIENTE autenticado; propietario e importes del servidor. |
| Consulta de órdenes/comprobantes | CLIENTE propietario u OPERADOR autorizado. |
| Descarga | CLIENTE propietario, orden PAID, pago SUCCESS y versión verificable. |
| Cuentas y roles | Superusuario; acceso al admin requiere además `is_staff`. |
| Extracción de fingerprint | Superusuario activo. |
| Eventos en admin | Consulta por superusuario; sin alta/edición/borrado desde ese administrador. |

Los eventos permiten trazabilidad sin guardar credenciales. La base no es
inmutable frente a sus administradores; no hay evidencia de un registro externo
append-only. La sesión web no reemplaza permisos de archivos ni de Windows.

## 6. Limitaciones históricas

La [auditoría existente](AUDITORIA_SEGURIDAD.md) conserva:

- **AUD-01:** cuatro PDF distintos ausentes; cuatro líneas pagadas afectadas.
- **AUD-02:** cuatro líneas sin versión, tres pagadas.
- **AUD-03:** dos comprobantes con pública `rsa-2026` ausente; tres comprobantes
  sí verificados con el material disponible.

No se ha demostrado falsificación ni acceso indebido por esos casos. El sistema
rechaza descargar sin versión/original confiable y no acepta una firma por faltar
su pública. Son limitaciones de disponibilidad y verificación que no se resuelven
generando PDF o claves nuevos.
