# amxtriage — Diagnóstico multilingüe y operaciones seguras del servidor

**Idioma / Bahasa / Language:** [English](PHASE7_MULTILANGUAGE.md) · [Bahasa Indonesia](PHASE7_MULTILANGUAGE.id.md) · [Español](PHASE7_MULTILANGUAGE.es.md)

**Estado:** 27 de octubre de 2026. Esta es una hoja de ruta, no una afirmación de que todas las funciones estén disponibles. Una función solo se considera terminada cuando su implementación y sus pruebas relevantes pasan.

## Funciones actuales

- CLI en Python 3.10+ para analizar registros de SA-MP/open.mp: errores de ejecución AMX, caídas y callbacks lentos reconocidos.
- Análisis, seguimiento de registros en crecimiento, líneas base, contexto de código fuente y recomendaciones locales basadas en reglas.
- El comando `diagnose` reconoce formatos habituales de compiladores/lint para Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go y Rust. No ejecuta compiladores ni cubre todas sus versiones.
- Las etiquetas del informe admiten inglés (`en`), indonesio (`id`) y español (`es`). La documentación principal está disponible en esos tres idiomas.
- La versión actual lee archivos locales, no inicia conexiones de red y no modifica el código fuente.

## Estado de los objetivos

| Área | Estado actual |
|---|---|
| Diagnóstico de logs SA-MP/open.mp | Base implementada; falta validar más formatos de servidores reales |
| CI, empaquetado y seguridad | Hay una base; todos los trabajos de CI deben pasar antes de declarar esta fase completa |
| Diagnósticos multilenguaje de compilador | Parsers iniciales y pruebas de formatos comunes; cobertura de versiones incompleta |
| Localización de CLI y Markdown | Etiquetas y documentación en en/id/es; parte de la ayuda y recomendaciones detalladas siguen en inglés |
| Catálogo de compatibilidad de plugins/dependencias | No implementado |
| Avisos dentro del juego a administradores/propietarios | No implementado |
| Mitigación DDoS de red e integración anti-cheat en el servidor | No implementado |
| Parches, validación y reversión | Solo hay recomendaciones; no existe un flujo de parche aplicado |

La documentación no cuenta como implementación. El progreso debe basarse en funciones y criterios de aceptación que tengan pruebas aprobadas.

## Tecnología y arquitectura

Mantén el núcleo en Python mientras sea mantenible y suficientemente rápido. La CLI no necesita compilación nativa para ejecutarse; usa GitHub Actions para probar y empaquetar. Considera Rust solo si el perfilado demuestra un problema de rendimiento o existe una necesidad de un binario nativo independiente.

Añade gradualmente:

- `core/`: modelo de diagnóstico, seguridad de archivos y coordinación.
- `adapters/<language>/`: parsers por lenguaje con fixtures de herramientas reales.
- `catalog/`: metadatos de versiones de servidor, plugin, componente, include, compilador y dependencias.
- `locales/`: traducciones de interfaz. Los ID de diagnóstico, las claves JSON, los códigos de salida y los identificadores oficiales deben permanecer estables.
- `fixes/`: generación de diffs, validación, checkpoint y reversión.
- `integrations/`: transportes de alertas explícitos y comprobables por separado.

Un árbol sintáctico no es un compilador y no demuestra corrección semántica. Añade parsers solo cuando exista una necesidad y fixtures de prueba.

## Idiomas y Markdown

Los idiomas documentados actualmente son inglés (`en`), indonesio (`id`) y español (`es`). Añade otros idiomas cuando las cadenas necesarias estén traducidas y existan pruebas de integridad de los catálogos. No traduzcas texto original de logs/compiladores, código fuente, nombres de archivo, plugins/natives, códigos de diagnóstico ni claves JSON.

## Catálogo de compatibilidad

Cada registro debe contener URL canónica del proyecto, enlace oficial de descarga/release, fuente de evidencia y fecha de comprobación, versión, servidor objetivo (SA-MP/open.mp), sistema operativo, arquitectura de CPU, ABI/bitness cuando corresponda, dependencias, tipo de instalación (`plugin` o `component`) y estado `verified`, `documented`, `unknown` o `incompatible`.

Que exista una descarga no prueba compatibilidad. No inventes enlaces ni descargues/ejecutes binarios de terceros automáticamente. Prioriza la documentación oficial, como la [instalación de open.mp](https://open.mp/docs/server/Installation) y la [configuración de open.mp](https://open.mp/docs/server/config.json). Si la evidencia es antigua o contradictoria, muestra `unknown` y explica por qué.

## Monitorización y límites de seguridad

El modo permanente debe ser un proceso/servicio visible, documentado y activado expresamente por el propietario; no un virus oculto ni un programa autorreplicable. No debe inyectar código en el proceso del juego, manipular memoria, evadir a administradores, cambiar el firewall en silencio ni ejecutar comandos extraídos de logs.

Mide CPU, RAM, E/S de disco y latencia con registros realistas. Limita tamaño de entrada, líneas, memoria, colas y frecuencia de notificación. Agrupa incidentes repetidos. La red debe estar desactivada por defecto; todo transporte remoto debe ser opt-in, autenticado y limitado. No es posible garantizar cero sobrecarga o el mismo ping en todos los hosts.

## DDoS, anti-cheat y avisos para administradores

Un analizador de logs no puede detener por sí solo un DDoS volumétrico; hacen falta filtros de red y mitigación del proveedor/hosting. No afirmes que existe protección DDoS solo por monitorizar logs. La detección anti-cheat debe ejecutarse de forma autoritativa en el servidor y tener en cuenta los falsos positivos. No hagas baneos automáticos por una sola señal débil.

Los avisos de chat dentro del juego **aún no están implementados**. Requieren un filterscript/plugin de SA-MP/open.mp probado o un puente local fiable. El prefijo, el texto del mensaje, la severidad, el cooldown y los destinatarios pueden ser configurables. La ruta del archivo y el número de línea deben provenir del diagnóstico estructurado y no se pueden sobrescribir desde la plantilla. La presentación objetivo es ruta roja y número de línea azul, usando el formato de color real de la API. Solo los administradores autorizados pueden recibirlos; los mensajes deben deduplicarse y limitarse. Los fallos de entrega no deben bloquear el servidor.

## Corrección segura

Modos previstos: `off` (solo diagnóstico), `suggest` (recomendación), `patch` (generar diff sin modificar archivos) y `apply` (aplicar solo tras aprobación explícita).

Cada parche debe quedar dentro de la raíz del proyecto, rechazar escapes de rutas/symlinks, comprobar que el archivo no cambió desde el análisis, crear un checkpoint, mostrar el diff, ejecutar el compilador/linter correcto y probar. Si falla la validación, hay que revertir y explicar el motivo. No instales plugins ni ejecutes scripts automáticamente a partir de logs o recomendaciones.

Que un compilador pase no garantiza que la lógica del juego sea correcta. Se necesitan pruebas de regresión y un servidor de staging. Ningún proceso puede garantizar honestamente una corrección del 100 % en todos los casos; el objetivo es evidencia, reproducibilidad y reversión segura.

## Orden de implementación

1. Pasar CI, pruebas entre versiones de Python, análisis estático, build de paquetes y smoke test de CLI.
2. Estabilizar los parsers y el contrato de los adaptadores con fixtures de regresión.
3. Añadir el adaptador de compilador Pawn con fixtures de herramientas oficiales.
4. Completar en/id/es y probar traducciones y esquema JSON estable.
5. Crear el catálogo de compatibilidad basado en evidencia upstream.
6. Definir y probar un esquema local de alertas antes de integrar avisos en el juego.
7. Añadir otros lenguajes solo con fixtures reales y herramientas de validación.
8. Añadir primero generación de parches; después aplicar con aprobación, checkpoint y reversión.
9. Integrar DDoS/anti-cheat solo con interfaces compatibles y revisión de seguridad.

CI es un control, no una garantía. No marques una etapa como terminada hasta que pasen sus trabajos y pruebas de comportamiento.
