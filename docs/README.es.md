# amxtriage — Análisis de registros de SA-MP/open.mp

**Idioma:** [English](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)  
**Hoja de ruta:** [Diagnóstico multilingüe y correcciones seguras](PHASE7_MULTILANGUAGE.md)

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
```

Desde el repositorio sin instalar:

```bash
PYTHONPATH=src python -m amxtriage analyze examples/sample_server_log.txt
```

Usa `amxtriage --help` o `amxtriage <command> --help` para ver las opciones. La selección de idioma para la salida CLI todavía está en la hoja de ruta; estas páginas multilingües solo traducen la documentación.

## Límites y seguridad

La versión actual lee archivos locales, no inicia conexiones de red y no modifica el código fuente. Las recomendaciones son sugerencias, no correcciones automáticas.

Actualmente amxtriage **no** es una defensa DDoS, no es un anti-cheat, no envía avisos al chat de administradores dentro del juego y no aplica parches automáticamente. El seguimiento de logs puede ayudar a detectar síntomas, pero detener un DDoS requiere mitigación de red/proveedor. El anti-cheat debe validarse en el servidor y evitar baneos automáticos basados en una única señal débil.

Consulta la [hoja de ruta](PHASE7_MULTILANGUAGE.md) para el diseño de avisos a administradores, idiomas, catálogo de compatibilidad de plugins y parches con validación y reversión.
