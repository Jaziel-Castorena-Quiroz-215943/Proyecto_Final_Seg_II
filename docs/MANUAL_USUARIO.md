# Manual de usuario

[Índice general](../README.md) · [Pruebas](PRUEBAS_EVIDENCIAS.md)

## 1. Acceso y precauciones

Usar `https://localhost:8443` con Caddy y Django preparados. No continuar ante
un certificado no confiable: consultar [HTTPS](HTTPS_PKI.md).
Los procedimientos que crean productos, usuarios, órdenes o pagos son
operaciones reales de la aplicación, aunque el pago sea simulado.
Para una demostración usar cuentas y datos de una instalación independiente;
esta documentación no ejecutó esos procedimientos sobre el histórico.

La navegación puede mostrar etiquetas según el idioma configurado. Las rutas
siguientes identifican funciones, no autorizan a eludir los formularios.
No enviar contraseñas, documentos de compra o PDF privados a servicios externos.

La interfaz utiliza estilos locales compartidos: navegación adaptable a pantallas
pequeñas, formularios y botones uniformes e indicadores de foco para teclado.
No requiere fuentes, hojas de estilo ni scripts de servicios externos.
Tras actualizar los estilos, publicar los archivos estáticos con `collectstatic`
como se indica en la [instalación](INSTALACION.md); Caddy los sirve desde
`staticfiles/`.

## 2. Funciones comunes

1. Consultar productos publicados desde `/catalog/`.
2. Registrarse en `/accounts/register/` con los datos propios del laboratorio.
   El registro crea CLIENTE, nunca operador o superusuario.
3. Iniciar sesión en `/accounts/login/`.
4. Consultar/actualizar el perfil en `/accounts/profile/`; el formulario no
   permite editar rol o privilegios.
5. Cerrar sesión con el formulario/botón correspondiente, que envía POST.

Si se olvida la contraseña, usar `/accounts/password-reset/`. La respuesta es
uniforme para no confirmar la existencia de una cuenta. En el entorno actual,
el mensaje se entrega a la consola del servidor y no a un correo real.
Los enlaces son sensibles, de un solo uso y caducan a la hora; no copiarlos
en capturas ni documentación.

## 3. CLIENTE

### Comprar y simular un pago

1. Iniciar sesión como CLIENTE y abrir un producto publicado.
2. Añadirlo al carrito `/cart/`. Solo hay una unidad de cada producto por
   carrito; se permite una compra posterior del mismo producto en otra orden.
3. Revisar la cotización y confirmar desde el formulario. Los precios
   provienen del servidor. Si la cotización expira tras 15 minutos o cambia
   el catálogo, actualizar el carrito y volver a revisar.
4. Abrir la orden desde `/orders/` y elegir el resultado del pago simulado.
   No se solicitan tarjetas ni hay transferencia bancaria.
5. El éxito cambia la orden a pagada y emite el comprobante en la misma
   transacción. El fallo deja una orden fallida; para otro intento se necesita
   una nueva orden. No crear órdenes adicionales solo porque se envió dos veces
   el mismo formulario: el sistema contempla idempotencia.

El historial muestra únicamente las órdenes propias, pendientes, pagadas y
fallidas. Una URL de otra persona no concede acceso.

### Comprobantes

Desde el detalle de la orden, abrir el comprobante cuando exista. Se puede
consultar el JSON y pegarlo en `/receipts/verify/` mediante el formulario
autenticado. La aplicación comprueba firma, integridad y relación con la compra.
El CLIENTE no puede verificar documentos de otra cuenta mediante esa interfaz.

No editar el JSON para «corregir» datos: la verificación lo rechazará.
El comprobante es independiente del PDF comprado y no es una factura fiscal.

### Descargar PDF

Solicitar la descarga mediante el botón de una línea pagada con versión
registrada. Se comprueba propietario, pago aprobado y original exacto.
Cada solicitud exitosa genera una copia personalizada; guardar esa copia si
se necesita conservar su binario exacto.

La marca no identifica públicamente al comprador por nombre, pero existe una
asociación interna protegida. No garantiza impedir copias ni sobrevivir a
alteraciones. La aplicación no archiva el binario personalizado para volver a
entregar exactamente la misma emisión.

## 4. OPERADOR

1. Recibir el rol de un superusuario autorizado; no hace falta ser `is_staff`.
2. Abrir `/catalog/manage/`.
3. Crear o editar nombre, descripción, precio, estado y archivo PDF.
4. Utilizar borrador para preparación, publicado para visibilidad pública y
   archivado para retirar de la oferta.
5. Subir PDF no cifrado, válido, de al menos una página y hasta 20 MiB.
   El hash lo calcula el servidor; el operador no lo escribe.
6. Consultar `/orders/` y comprobantes para soporte. No se permite pagar ni
   descargar como si se fuera el cliente.

No borrar versiones antiguas del almacenamiento: pueden estar referenciadas
por compras. El panel no proporciona una URL pública al original.
La validación de formato no equivale a antivirus.

## 5. ADMINISTRADOR y superusuario

El rol ADMINISTRADOR **no concede por sí solo** acceso a administración,
catálogo, órdenes ni extracción. Para el panel `/admin/`, el usuario debe estar
activo, tener acceso administrativo Django (`is_staff`) y ser superusuario
para los módulos de cuentas/eventos protegidos.

Un superusuario autorizado puede:

- Gestionar cuentas y asignar roles desde la sección de usuarios.
- Consultar eventos de seguridad sin modificarlos ni borrarlos desde ese panel.
- Abrir `/security/fingerprints/extract/`, enviar una copia emitida de prueba
  sin alteraciones y consultar su asociación si identificador y hash coinciden.

Asignar OPERADOR no requiere otorgar `is_superuser`. Para mantener separación
de funciones, utilizar cuentas distintas para operación comercial y
administración. No cambiar roles de cuentas reales para demostrar el manual.
La extracción revela datos internos: no publicar el resultado con identidades.

## 6. Errores y límites conocidos

| Situación | Acción segura |
| --- | --- |
| Redirección a login o 403 | Comprobar sesión/rol; no alterar parámetros para eludir permisos. |
| 404 al abrir una orden ajena | Comportamiento de aislamiento; no supone que pueda enumerarse el recurso. |
| CSRF rechazado | Volver al formulario y revisar origen HTTPS; no deshabilitar protección. |
| 409 en descarga | Falta versión/original verificable o no es procesable; solicitar revisión sin sustituir el PDF histórico. |
| 503 al emitir/verificar | Revisar claves/configuración o conflicto temporal según el mensaje; no marcar manualmente el pago como exitoso. |
| Documento modificado o marca no recuperable | Conservar el archivo y reportar; no afirmar atribución sin coincidencia exacta. |

La [auditoría](AUDITORIA_SEGURIDAD.md) documenta tres limitaciones históricas:
cuatro PDF distintos ausentes; cuatro líneas sin versión, tres pagadas; dos
comprobantes con pública histórica ausente. No son accesos indebidos demostrados.
Su existencia no autoriza a regenerar documentos, claves o registros anteriores.
