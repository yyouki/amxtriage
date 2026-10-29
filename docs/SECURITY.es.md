# Política de seguridad

**Idioma / Bahasa / Language:** [English](../SECURITY.md) · [Bahasa Indonesia](SECURITY.id.md) · [Español](SECURITY.es.md)

## Cómo informar de una vulnerabilidad

No publiques secretos, pasos de explotación ni registros privados del servidor en un issue público.

Si el repositorio tiene activado el informe privado de vulnerabilidades, utiliza la pestaña **Security**. Si no está disponible, abre un issue breve para solicitar que los responsables habiliten un canal privado; no incluyas detalles de explotación ni credenciales en ese issue público.

Incluye la versión/commit afectado, el sistema operativo, la versión de Python y una reproducción mínima sin información sensible. Nunca incluyas credenciales RCON, contraseñas de jugadores, tokens de acceso ni datos privados de clientes.

## Alcance y valores seguros por defecto

amxtriage es una utilidad local para analizar registros y dispone de un bridge opcional de alertas de diagnóstico. No es un servicio de mitigación DDoS. Informa de posibles problemas en el manejo de rutas, ejecución de datos procedentes de registros, omisión de controles de autorización del bridge o modificaciones inesperadas del código fuente.

Este documento no promete un SLA de respuesta.
