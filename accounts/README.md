# Cuentas

El usuario personalizado se configura mediante `AUTH_USER_MODEL` antes de aplicar
cualquier migración. La migración inicial está incluida en el proyecto; la
base activa documentada en la auditoría ya contiene las tablas de cuentas.
No se debe cambiar `AUTH_USER_MODEL` después de crear las tablas sin planificar una
migración específica de datos.

## Funcionalidad y privilegios

Las rutas comienzan en `/accounts/`: `register/`, `login/`, `logout/`,
`profile/` y `password-reset/`. El cierre de sesión requiere POST y todos los
formularios utilizan CSRF. El perfil exige autenticación y solo permite cambiar
nombre, apellido y correo. El registro siempre crea un CLIENTE sin privilegios.
El correo es obligatorio en los formularios y único sin distinguir mayúsculas;
la contraseña se valida en el servidor y se almacena con Argon2id.

Los roles CLIENTE, OPERADOR y ADMINISTRADOR son etiquetas de negocio, **no**
conceden permisos de Django automáticamente. El panel del catálogo comprueba
explícitamente el rol OPERADOR. Únicamente un superusuario puede
gestionar usuarios, roles y privilegios desde el administrador; incluso un usuario
con rol ADMINISTRADOR o permisos de Django necesita ser superusuario para ello.
Los superusuarios creados con `createsuperuser` reciben el rol ADMINISTRADOR por
defecto. La autorización de futuras funciones debe comprobar explícitamente los
permisos o roles necesarios.

La recuperación muestra la misma respuesta para correos existentes e inexistentes;
los enlaces son de un solo uso y caducan a la hora. Los eventos registran fecha,
tipo y usuario cuando se conoce, sin contraseñas ni tokens. Los intentos fallidos y
solicitudes de recuperación no almacenan identificadores. En el administrador solo
un superusuario puede consultarlos y no puede modificarlos ni borrarlos desde allí.
La base de datos no constituye un registro inmutable frente a sus administradores.

## Despliegue

La configuración predeterminada es exclusivamente para desarrollo: DEBUG está
activado, se usa una clave local y los correos se imprimen en consola. Antes de
producción, establecer `DJANGO_DEBUG=false`, una `DJANGO_SECRET_KEY` larga y
aleatoria, y `DJANGO_ALLOWED_HOSTS` con los dominios separados por comas. Configurar
un backend de correo real y remitente mediante `MAILERS` y `DEFAULT_FROM_EMAIL`.
Servir exclusivamente por HTTPS; con DEBUG desactivado las cookies de sesión y
CSRF se marcan Secure. Proteger secretos, acceso y copias de la base de datos, y
definir retención y monitoreo de eventos.

Para el entorno local ya preparado, `.env` activa el perfil HTTPS con DEBUG
desactivado y el lanzador recupera secretos mediante DPAPI. Consulta
[la instalación nueva](../docs/INSTALACION.md) y
[HTTPS con Caddy](../docs/HTTPS_PKI.md), sin reinicializar la base existente.

Este módulo no implementa límites de intentos, CAPTCHA, MFA ni verificación de
propiedad del correo: deben añadirse antes de exponerlo públicamente. La respuesta
uniforme de recuperación no elimina posibles diferencias de tiempo o entrega.
