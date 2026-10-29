# Guía de publicación, plataformas y proveedores de alojamiento

**Idioma / Bahasa / Language:** [English](RELEASE_AND_PLATFORM_SUPPORT.md) · [Bahasa Indonesia](RELEASE_AND_PLATFORM_SUPPORT.id.md) · [Español](RELEASE_AND_PLATFORM_SUPPORT.es.md)

Esta guía diferencia el soporte probado de la portabilidad posible. No certifica todos los proveedores de alojamiento ni todas las compilaciones de sistemas operativos.

## Descripción sugerida del repositorio de GitHub

> Análisis de registros multiplataforma para SA-MP/open.mp: errores de ejecución Pawn, caídas, diagnósticos de compilador y alertas administrativas. Incluye CLI, GUI de escritorio, vista previa/aplicación segura de parches y catálogo de compatibilidad de plugins.

Temas sugeridos: `samp`, `openmp`, `pawn`, `log-analysis`, `server-monitoring`, `python`, `developer-tools`.

## Matriz de soporte de ejecución

| Objetivo | Estado de soporte actual |
|---|---|
| Windows de escritorio | CLI probada con Python 3.10–3.13; la GUI necesita Tkinter. |
| macOS de escritorio | CLI probada con Python 3.10–3.13; la GUI necesita Tkinter. |
| Linux de escritorio/servidor | CLI probada con Python 3.10–3.13; la GUI necesita Tkinter y una sesión gráfica. Las métricas son opcionales y solo para Linux. |
| Servidor Linux sin interfaz gráfica | CLI y monitor adecuados; la GUI no puede ejecutarse sin pantalla de escritorio. |
| Android | No se distribuye una app nativa Android ni existe un objetivo CI. |
| iOS/iPadOS | No se distribuye una app nativa iOS ni existe un objetivo CI. |
| BSD/otros Unix | No está certificado por la matriz CI actual. |
| Bridge Pawn para SA-MP | Objetivo CI: `pawn-lang/compiler v3.10.10` con `samp-stdlib` fijado; la entrega real requiere pruebas en staging. |
| Bridge Pawn para open.mp | Objetivo CI: `openmultiplayer/compiler v3.10.11` con `omp-stdlib` fijado; la entrega real requiere pruebas en staging. |
| Otras versiones de compilador Pawn | No están garantizadas. Compila y prueba en staging con el compilador e includes exactos. |

“Multiplataforma” no significa que se hayan probado todos los SO, arquitecturas CPU, versiones de Python, ABI de plugins o compiladores. Solo las combinaciones mencionadas en CI están verificadas a nivel de compilación/pruebas.

## Proveedores de alojamiento y límites frente a DDoS

No existe una API de gestión única compartida por todos los proveedores. Sus APIs, permisos de cuenta, planes, protocolos, modelos de firewall y capacidades de mitigación son diferentes.

| Proveedor/producto | Capacidad documentada oficialmente | Estado de amxtriage |
|---|---|---|
| Cloudflare Spectrum | Se pueden crear aplicaciones Spectrum desde el panel o la API; el soporte UDP y los campos disponibles dependen del plan. [Guía oficial](https://developers.cloudflare.com/spectrum/get-started/). | No hay adaptador de API automático. |
| OVHcloud Game DDoS Protection | OVH documenta funciones de Game Firewall y protocolos de juego por IP mediante API. [Guía oficial](https://docs.ovhcloud.com/en/guides/bare-metal-cloud/dedicated-servers/firewall-game-ddos). | No hay adaptador de API automático. |
| AWS Shield Advanced | Dispone de una API específica para protecciones, ataques y recursos relacionados. [Operaciones oficiales](https://docs.aws.amazon.com/waf/latest/DDOSAPIReference/API_Operations.html). | No hay adaptador automático; hay que confirmar la arquitectura del endpoint de juego. |
| DigitalOcean Cloud Firewalls | Las reglas de API controlan el tráfico hacia/desde Droplets; esto no garantiza por sí mismo mitigación DDoS volumétrica específica para juegos. [API oficial](https://docs.digitalocean.com/products/networking/firewalls/reference/api/). | No hay adaptador de API automático. |
| Hetzner Cloud Firewalls | La API permite gestionar reglas de entrada/salida; esas reglas no equivalen a una mitigación DDoS universal. [API oficial](https://docs.hetzner.cloud/reference/cloud). | No hay adaptador de API automático. |
| Otros proveedores y paneles reseller | Las APIs y productos de protección varían; algunos proveedores no ofrecen API pública. | Configuración manual hasta documentar y probar un adaptador específico. |

El bridge Pawn es una alerta diagnóstica local, no una mitigación DDoS ni un anti-cheat. Analizar registros no puede detener un tráfico que ya ha saturado la conexión ascendente.

Un adaptador real necesita endpoints documentados, el identificador del recurso protegido, permisos mínimos, opt-in explícito, modo dry-run, auditoría y pruebas en staging. No debe bloquear direcciones ni modificar firewalls automáticamente basándose solo en señales heurísticas de los registros.

## Configuración recomendada del repositorio GitHub

La descripción y los temas son metadatos de GitHub, no archivos fuente. Recomendaciones para un lanzamiento público:

1. **About:** usa la descripción y los temas anteriores; deja Website vacío salvo que exista un sitio oficial.
2. **Rama/reglas:** conserva `main` como rama predeterminada. Exige CI aprobado, bloquea force-push y eliminación de ramas, y exige pull requests a colaboradores externos.
3. **Actions:** aplica permisos mínimos. El CI actual necesita `contents: read`. Antes de una versión estable reforzada, fija las GitHub Actions de terceros a SHA de commit revisadas.
4. **Seguridad:** activa alertas/actualizaciones de Dependabot, escaneo de secretos y protección de push cuando estén disponibles. Prepara `SECURITY.md` e informes privados de vulnerabilidades si existen.
5. **Calidad de lanzamiento:** mantén changelog, política de versiones/tags, notas de versión, wheel y distribución fuente, checksums de artefactos bridge y guía de staging/rollback.
6. **Issues:** solicita SO, versión de Python, tipo/versión del servidor, versión de compilador y un registro mínimo anonimizado. No adjuntes credenciales RCON, contraseñas de jugadores ni datos privados del host.

La conexión GitHub disponible para esta tarea puede modificar archivos fuente y consultar metadatos, pero no puede editar la descripción/temas de About ni las reglas de rama. Aplica esos cambios mediante Settings/About de GitHub.

## Lista de aceptación de lanzamiento

- [ ] CI pasa para Python 3.10–3.13 y ambas combinaciones indicadas de compilador/includes Pawn.
- [ ] Bridge probado en staging con la versión exacta del servidor y los permisos correctos.
- [ ] GUI probada en escritorio Windows/macOS/Linux; CLI funcional en Linux sin interfaz gráfica.
- [ ] La documentación en inglés, indonesio y español se enlaza entre sí.
- [ ] Las combinaciones desconocidas de proveedor/compilador/plataforma permanecen como desconocidas.
- [ ] No hay secretos de producción ni registros privados en fixtures/artefactos.
- [ ] Existen changelog, canal de seguridad, notas de versión e instrucciones de rollback.
