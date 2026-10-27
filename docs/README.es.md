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

## Exportación local de alertas

`amxtriage watch server_log.txt --alert-jsonl alerts.jsonl` exporta eventos nuevos a un archivo local JSONL para que un puente independiente los procese. **No envía mensajes al chat del juego por sí mismo.** La ruta y la línea permanecen como campos estructurados separados del texto configurable; los metadatos de color indican ruta roja y línea azul, pero el puente debe aplicar los códigos reales de la API. Los fallos de exportación no deben detener el seguimiento del log.

## Límites y seguridad

La versión actual lee archivos locales; los comandos `catalog` y `watch --alert-jsonl` no inician conexiones de red. Las recomendaciones siguen siendo sugerencias, no correcciones automáticas.

Actualmente amxtriage **no** es una defensa DDoS, no es un anti-cheat, no envía avisos directamente al chat de administradores dentro del juego y no aplica parches automáticamente. El seguimiento de logs puede ayudar a detectar síntomas, pero detener un DDoS requiere mitigación de red/proveedor. El anti-cheat debe validarse en el servidor y evitar baneos automáticos basados en una única señal débil.

Consulta la [hoja de ruta en español](PHASE7_MULTILANGUAGE.es.md) y el [progreso del proyecto](PROGRESS.md) para ver los límites y los siguientes pasos.
