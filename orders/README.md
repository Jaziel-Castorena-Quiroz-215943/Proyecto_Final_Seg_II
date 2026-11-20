# Carrito y órdenes

## Acceso y flujo

Un CLIENTE autenticado añade o elimina productos en `/cart/`. Solo los productos
publicados pueden añadirse y hay una unidad de cada producto por carrito. Un
producto previamente comprado puede comprarse otra vez en una orden nueva.
La creación de órdenes y el pago requieren POST y CSRF. Las órdenes aparecen en
`/orders/`: el CLIENTE ve solo las suyas y el OPERADOR puede consultar todas,
sin modificarlas ni pagar. ADMINISTRADOR no tiene acceso a estas funciones por
su rol; el superusuario tampoco recibe acceso implícito. Los accesos a órdenes
ajenas devuelven 404.

El carrito muestra los precios actuales. La cotización firmada caduca a los
15 minutos; si los productos, nombres, precios o disponibilidad cambian antes
de confirmar, se rechaza la operación y el cliente debe actualizar el carrito.
Los importes se obtienen del catálogo en el servidor, no de campos de precio
enviados por el navegador. La orden conserva nombre y precio unitario históricos
y el total calculado al confirmar. No se presupone una moneda.

La orden empieza pendiente. El cliente elige simular éxito o fallo: no se
recopilan datos bancarios, no hay proveedor ni transacción real. El éxito emite
un comprobante firmado en la misma transacción; si no se pueden cargar las claves,
el pago permanece pendiente y se devuelve 503. Una orden
fallida no puede pagarse otra vez; para otro intento hay que crear una nueva.
El historial incluye órdenes pendientes, pagadas y fallidas.
Las órdenes nuevas guardan también la versión del PDF para su posterior descarga
personalizada; las órdenes antiguas sin versión registrada no son descargables.

## Integridad y seguridad

La clave única de confirmación identifica cada carrito confirmado: repetir el
mismo envío devuelve la misma orden, sin crear otra. Se rota la clave al
confirmar y se vacía el carrito en la misma transacción. Cada orden tiene como
máximo un pago simulado: repetir el mismo resultado es idempotente y solicitar
un resultado contradictorio devuelve 409. La transición de estado, el pago y
su evento se guardan atómicamente. Las restricciones de base de datos impiden
elementos duplicados y estados o importes inválidos; las operaciones bloquean
las filas relevantes cuando la base de datos lo admite. En SQLite, un conflicto
de bloqueo devuelve 503 con `Retry-After`, para reintentar la misma solicitud.

Se registran eventos de creación de orden, resultado del pago, acceso denegado y
conflicto, sin importar importes o datos sensibles enviados por el cliente. Los
eventos se gestionan mediante el módulo de cuentas; sus limitaciones de auditoría
siguen siendo aplicables. Véase [comprobantes](../receipts/README.md) para sus
claves externas y verificación, y [huellas y descargas](../security/README.md)
para los PDF personalizados. La firma de la cotización solo protege su integridad.

Las migraciones de `accounts`, `cart` y `orders` están incluidas y la base
activa auditada ya contiene sus tablas. Las primeras pruebas usaron tablas
temporales en memoria; véanse los resultados y el procedimiento actual en
[pruebas y evidencias](../docs/PRUEBAS_EVIDENCIAS.md).
No aplicar instrucciones de inicialización nueva a los datos conservados.
