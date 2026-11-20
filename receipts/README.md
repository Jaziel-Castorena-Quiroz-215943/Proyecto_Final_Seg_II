# Comprobantes firmados

Cada nuevo pago simulado exitoso emite exactamente un comprobante dentro de la
misma transacción que el pago. Si falla la emisión, el pago permanece pendiente.
Un pago fallido no genera comprobante. Los pagos exitosos anteriores a este
módulo no se modifican ni reciben comprobantes automáticamente.

El detalle de la orden enlaza al comprobante. El CLIENTE puede consultar y
verificar únicamente sus comprobantes; el OPERADOR puede consultar y verificar
todos, sin modificarlos. ADMINISTRADOR no obtiene acceso implícito. El documento
JSON está disponible desde la vista del comprobante y puede pegarse en
`/receipts/verify/`; la verificación web requiere autenticación y CSRF, comprueba
la firma, la integridad y la correspondencia con la orden y el pago guardados.
Los comprobantes alterados se rechazan. Las consultas privadas no se almacenan
en caché. Las descargas personalizadas de productos se documentan por separado
en [huellas y descargas](../security/README.md).

## Claves externas

Antes de aprobar pagos exitosos, configurar estas variables de entorno:

- `DJANGO_RECEIPTS_PRIVATE_KEY_PATH`: ruta absoluta del archivo PEM privado RSA,
  **fuera del directorio del proyecto** y de cualquier directorio público.
- `DJANGO_RECEIPTS_PRIVATE_KEY_PASSWORD`: contraseña del PEM, si está cifrado.
  Suministrarla mediante el mecanismo de secretos del despliegue, no en código.
- `DJANGO_RECEIPTS_PUBLIC_KEYS_DIR`: ruta absoluta del directorio de claves
  públicas PEM de confianza.
- `DJANGO_RECEIPTS_KEY_ID`: identificador de la clave activa, con letras ASCII,
  números, guion o guion bajo, hasta 64 caracteres. La clave pública debe estar
  en `<directorio>/<identificador>.pem`.

Las claves deben ser un par RSA de al menos 2048 bits; se recomienda generar
3072 bits con una herramienta de confianza y proteger la clave privada con
cifrado y ACL restrictivas. La aplicación comprueba que el par coincida. Debe
restringirse la escritura del directorio de claves públicas: esas claves son
anclas de confianza, no se aceptan claves enviadas dentro del documento. Nunca
se generan ni almacenan claves privadas en el proyecto o en la base de datos.
En Windows configurar ACL explícitas y proteger también los respaldos y secretos.

Para rotar claves, generar un nuevo par, añadir su PEM público con otro
identificador y cambiar la ruta privada y el identificador activo. Conservar
las claves públicas antiguas para verificar comprobantes anteriores; si falta
una clave necesaria, la consulta devuelve 503. La gestión de revocación,
compromiso y distribución de claves confiables corresponde al despliegue.

## Formato y verificación

El objeto JSON contiene `body`, `sha256` y `signature`. El cuerpo incluye versión,
algoritmo, identificador de clave, identificadores del comprobante, usuario,
orden y pago, fechas, tipo de pago simulado, total y líneas históricas. El
resumen es SHA-256 de los bytes UTF-8 del cuerpo serializado con
`json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)`.
La firma es RSA-PSS sobre esos bytes, con SHA-256, MGF1-SHA256 y sal de 32
bytes; se codifica en Base64. Para verificación independiente se debe obtener
la clave pública confiable por un canal seguro y comprobar **tanto** el resumen
como la firma y el significado de los datos. El identificador de clave está
incluido en el cuerpo firmado. La firma acredita integridad y posesión de la
clave, no convierte un pago simulado en un pago real ni en una factura fiscal.

La emisión, las verificaciones, los documentos inválidos, los accesos denegados
y los errores de emisión generan eventos de seguridad sin claves ni documentos.
La base de datos de eventos no es inmutable frente a sus administradores.

## Archivos y pruebas

`models.py` conserva el documento y su firma; `crypto.py` carga y valida claves,
firma y verifica; `services.py` emite y comprueba la relación con el pago;
`views.py`, `forms.py`, `urls.py` y las plantillas ofrecen acceso controlado.
El servicio de órdenes integra la emisión transaccional. `tests.py` cubre
verificación criptográfica independiente, alteración, permisos, CSRF, rotación,
reintentos, retrocompatibilidad y rollback. Las pruebas existentes de órdenes
usan claves temporales cifradas generadas solo para pruebas.

Las primeras pruebas crearon tablas directamente en memoria. La auditoría
posterior ejecutó la suite Django con migraciones únicamente sobre su base
de pruebas en memoria, sin modificar la base real. Para repetir con secretos,
PDF y claves efímeros, seguir
[pruebas y evidencias](../docs/PRUEBAS_EVIDENCIAS.md) y el bloque de ejecución
aislada del informe enlazado allí.

Las migraciones están incluidas y la base activa auditada ya contiene
comprobantes y eventos. No aplicar instrucciones de instalación nueva al
histórico ni reemitir comprobantes para completar registros anteriores.
