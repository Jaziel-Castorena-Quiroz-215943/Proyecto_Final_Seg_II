# Catálogo de productos PDF

`/` presenta la página principal, `/catalog/` muestra los productos publicados y
`/catalog/<id>/` muestra su detalle. Los borradores y archivados no aparecen ni
pueden consultarse mediante las vistas públicas. Los clientes pueden crear
órdenes con pagos simulados y descargar copias personalizadas de las versiones
registradas en sus órdenes pagadas; no existen pagos reales.

El panel `/catalog/manage/` permite crear y editar productos y cambiar su estado
entre borrador, publicado y archivado. Solo acceden usuarios activos con rol
OPERADOR; no necesitan `is_staff`. CLIENTE, ADMINISTRADOR y superusuarios sin el
rol OPERADOR no pueden acceder. La asignación de roles sigue reservada a los
superusuarios en el administrador de cuentas. Los formularios utilizan CSRF.

El precio es decimal no negativo; no se presupone ninguna moneda. Cada PDF debe
tener extensión y cabecera PDF válidas, contener al menos una página, no estar
cifrado ni necesitar reparación y medir como máximo 20 MiB. El servidor calcula
SHA-256 sobre los bytes recibidos al crear o reemplazar el archivo; no acepta un
hash del formulario. Esta validación estructural no es un antivirus ni garantiza
que el documento carezca de contenido activo o malicioso.

Los archivos reciben nombres aleatorios y se guardan por defecto fuera del
directorio del proyecto, en `Proyecto Final - archivos privados`, junto a este.
`DJANGO_PRIVATE_CATALOG_ROOT` permite configurar otra ruta privada. El almacenamiento
no ofrece URL y las páginas no exponen nombres ni rutas de archivo. El operador ve
el hash, pero tampoco recibe un enlace al PDF. Los archivos anteriores y los
que hayan quedado huérfanos por fallos o reversiones no se eliminan automáticamente.
Antes de limpiar archivos antiguos, comprobar que ninguna orden conserva una
referencia a esa versión: eliminarla impediría la descarga correspondiente.

En despliegue, configurar el servidor y proxy para que **nunca** publiquen ese
directorio, no colocarlo dentro de medios o estáticos públicos, y restringir sus
permisos y copias de seguridad al proceso de la aplicación. En Windows se deben
configurar las ACL del sistema de archivos: los modos POSIX no garantizan protección.
Limitar también el tamaño de las solicitudes en el proxy y analizar los archivos
con herramientas de seguridad adecuadas. Véase [huellas y descargas](../security/README.md).

La migración inicial está incluida y la base activa auditada contiene el
catálogo. Las primeras pruebas del módulo utilizaron tablas temporales en
memoria; los resultados actuales y el procedimiento aislado están en
[pruebas y evidencias](../docs/PRUEBAS_EVIDENCIAS.md).
No ejecutar migraciones sobre la base conservada para seguir esta documentación.
