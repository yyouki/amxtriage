# amxtriage — Análisis de registros de SA-MP/open.mp

**Idioma:** [English](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)  
**Hoja de ruta:** [Diagnóstico multilingüe y correcciones seguras](PHASE7_MULTILANGUAGE.es.md)

amxtriage es una herramienta CLI en Python para resumir problemas registrados en logs de SA-MP/open.mp: errores de ejecución AMX, caídas y callbacks lentos reconocidos en los formatos de log compatibles. Ayuda a encontrar patrones repetidos y, cuando los datos están disponibles, la ubicación del archivo y la línea de código.

## Funciones disponibles

- Analiza logs de texto, archivos `.gz` y la entrada estándar.
- Agrupa errores similares y cuenta sus apariciones.
- Muestra contexto de archivos Pawn si está disponible.
- Modo `watch` para seguir un log que crece.
- Línea base para comparar problemas nuevos.
- Recomendaciones de diagnóstico basadas en reglas y sin conexión.

## Instalación

Requiere Python 3.10 o posterior.

```bash
python -m pip install .
amxtriage analyze server_log.txt
amxtriage watch server_log.txt --poll-interval 1
amxtriage recommend server_log.txt
amxtriage catalog --server open.mp
```

Desde el repositorio sin instalar:

```bash
PYTHONPATH=src python -m amxtriage analyze examples/sample_server_log.txt
```

Las etiquetas de los informes CLI admiten inglés (`en`, predeterminado), indonesio (`id`) y español (`es`). El idioma se puede indicar antes o después del subcomando:

```bash
amxtriage --language es analyze server_log.txt
amxtriage analyze server_log.txt --lang es
amxtriage recommend server_log.txt --language id
```

La traducción del CLI es gradual: las etiquetas y los títulos del informe están traducidos, pero las recomendaciones diagnósticas detalladas, algunos mensajes de ayuda y el texto original de los logs/compiladores pueden seguir en inglés. Las claves JSON permanecen en inglés y estables para no romper la automatización. Usa `amxtriage --help` o `amxtriage <command> --help` para ver otras opciones.

## Catálogo de compatibilidad

El catálogo local ofrece filtros por servidor y estado, y exportación text/Markdown/JSON:

```bash
amxtriage catalog
amxtriage catalog --server open.mp --format markdown -o plugin-catalog.md
amxtriage plugins --format json -o plugin-catalog.json
```

Las entradas actuales son `documented` a partir de la guía oficial de instalación de open.mp; no son pruebas de compatibilidad en tiempo de ejecución. Los campos de sistema operativo/versiones vacíos indican que la fuente no los especifica. El comando no descarga ni ejecuta binarios.

## Alertas locales y avisos en el chat de administradores

Para exportar eventos estructurados sin integración con el juego, usa JSONL:

```bash
amxtriage watch server_log.txt --alert-jsonl alerts.jsonl
```

Para enviar avisos mediante el filterscript Pawn opcional, utiliza un archivo de protocolo local:

```bash
amxtriage watch server_log.txt --alert-pawn-file ./scriptfiles/amxtriage-alerts.txt
```

El source está en [`amxtriage_bridge.pwn`](../integrations/pawn/amxtriage_bridge.pwn) y las instrucciones en [integrations/pawn/README.md](../integrations/pawn/README.md). El propietario debe compilar y cargar el filterscript de forma explícita; amxtriage no modifica la configuración del servidor.

Por defecto, el bridge envía mensajes solo a administradores autenticados por RCON, procesa como máximo cinco registros por segundo y muestra la ruta del archivo en rojo y el número de línea en azul. La ubicación procede de campos de diagnóstico estructurados y no puede ser sobrescrita por una plantilla de texto. El watcher y el servidor deben tener permisos de archivo compatibles; en POSIX, los archivos de alertas nuevos se crean con permisos `0600`.

**Estado de las pruebas:** el source Pawn se compila en GitHub Actions con el compilador e includes fijados. El envío de mensajes aún no se ha probado de extremo a extremo en un servidor staging real de SA-MP/open.mp. Compilar no demuestra compatibilidad en tiempo de ejecución ni garantiza que el ping no cambie. Este bridge solo informa de problemas de diagnóstico; no es un sistema anti-cheat ni mitiga DDoS.

## Vista previa segura del parche (solo diff)

El comando `patch-preview` crea un diff para un único caso Pawn muy concreto: el error de compilador `001` indica que falta un punto y coma justo antes de `return`, y la línea anterior es una asignación/declaración sencilla. El archivo fuente debe resolverse de forma única y segura dentro de `--source-dir`.

```bash
amxtriage patch-preview compile.log --source-dir . --format unified
amxtriage patch-preview compile.log --source-dir . --format json -o vista-previa-parche.json
```

Esto **no** es un reparador automático general. No modifica el código, no aplica parches, no descarga dependencias y no ejecuta el compilador. Los casos ambiguos o no admitidos se rechazan. El formato `unified` acepta un solo log de compilación después de expandir comodines y muestra únicamente el diff; si no hay una opción segura, explica el motivo en stderr y termina con el código `3`. Revisa el diff, compila con el compilador Pawn oficial y ejecuta pruebas de regresión/juego antes de usarlo.

## Límites y seguridad

La versión actual lee archivos locales; los comandos `catalog` y `watch --alert-jsonl` no inician conexiones de red. Las recomendaciones siguen siendo sugerencias, no correcciones automáticas.

Actualmente amxtriage **no** es una defensa DDoS ni un anti-cheat y no tiene modos automáticos de patch/apply. La exportación de alertas y el source del bridge Pawn están disponibles y el bridge compila en CI, pero el envío al chat del juego todavía no se ha verificado en un servidor staging real. El seguimiento de logs puede ayudar a detectar síntomas, pero detener un DDoS requiere mitigación de red/proveedor. El anti-cheat debe validarse en el servidor y evitar baneos automáticos basados en una única señal débil.

Consulta la [hoja de ruta en español](PHASE7_MULTILANGUAGE.es.md) y el [progreso del proyecto](PROGRESS.md) para ver los límites y los siguientes pasos.
