# Descargas y huellas PDF

Al crear una orden nueva se guarda, en cada línea, el nombre privado y el SHA-256
del PDF que estaba en el catálogo en ese momento. Tras un pago aprobado, solo
el CLIENTE propietario de la orden puede solicitar su descarga mediante POST con
CSRF. Se comprueban tanto el estado pagado como el resultado exitoso del pago.
Los operadores y otros clientes no pueden descargar el producto de esa orden.
Las órdenes antiguas sin versión registrada no permiten descarga: no se infiere
una versión histórica a partir del producto actual.

El servidor lee el original desde el almacenamiento privado, comprueba su
SHA-256 y genera una copia en memoria mediante PyMuPDF; no modifica el original.
Cada solicitud exitosa añade en cada página una marca visible `FPR-` seguida de un
identificador aleatorio de 128 bits, e incrusta ese identificador como archivo
interno del PDF. No añade nombres, correos ni identificadores de usuario, orden o
producto al PDF. Los metadatos o contenidos que ya existían en el original no se
eliminan ni se inspeccionan para detectar datos personales. Se registra por cada
emisión la asociación entre identificador, usuario y línea de orden, junto con el
SHA-256 exacto de la copia emitida. Una solicitud que falla durante la generación
no produce una descarga registrada; el registro indica emisión, no que la red
haya entregado el archivo por completo.

El botón aparece en el detalle de una orden pagada con versión registrada. Una
versión ausente, alterada, no accesible o no procesable se rechaza; no se entrega
el original como alternativa. Los PDF con indicador de firmas digitales o campos
de firma se rechazan para evitar invalidar firmas existentes. Esta comprobación
no sustituye la verificación criptográfica de firmas PDF. Los comprobantes de pago
firmados son independientes y no se modifican.

## Extracción y límites

Solo un superusuario autenticado puede enviar un PDF mediante POST a
`/security/fingerprints/extract/`. Se extrae el identificador, se busca el registro
interno y se comprueba que el SHA-256 coincida exactamente con la copia emitida
antes de revelar usuario, orden y producto. El acceso a la asociación, incluso
mediante consultas directas a la base de datos o respaldos, debe restringirse:
el identificador es seudónimo, pero puede asociarse a una persona internamente.
Se registran eventos de emisión, denegación, error y extracción o documento inválido.

La marca **no es DRM ni una huella resistente a manipulación**. Puede eliminarse
o alterarse; una impresión, captura, reescritura o modificación del PDF puede
impedir su identificación. Copiar un identificador a otro PDF no permite
atribuirlo como el original emitido porque no coincidirá su SHA-256. El original
privado tampoco queda protegido frente a quien tenga acceso administrativo al
almacenamiento o pueda revertir la personalización de su propia copia.

Los originales comprados y los registros de huellas deben conservarse conforme a
la política de retención: borrar una versión antigua impide nuevas descargas de
esa orden. Proteger almacenamiento, ACL, respaldos, registros y los archivos
temporales de subida de Django. La personalización acepta originales de hasta
20 MiB y documentos resultantes o enviados para extracción de hasta 30 MiB;
limitar también el tamaño de solicitudes en el proxy. La comprobación de formato
no reemplaza el análisis antivirus ni garantiza que un PDF carezca de contenido
activo. En producción, definir controles de acceso, retención y límites de uso.

## Cambios y pruebas

`fingerprinting.py` valida el original, crea y recupera las marcas; `models.py`
conserva sus asociaciones; `views.py`, `forms.py`, `urls.py` y la plantilla
restringen descargas y extracción. Las órdenes guardan la versión en el checkout;
los eventos se integran en `accounts`. Las pruebas cubren versiones históricas,
repeticiones, marcas visibles y recuperables, permisos, CSRF, alteraciones,
PDF con campos de firma y compatibilidad con los comprobantes.

Las migraciones están incluidas y la base activa auditada contiene los registros
de fingerprinting. La suite actual aplica migraciones solo a la base de pruebas
en memoria. Para repetir sin tocar el histórico, seguir
[pruebas y evidencias](../docs/PRUEBAS_EVIDENCIAS.md), que incluye `security`
en el procedimiento aislado.
