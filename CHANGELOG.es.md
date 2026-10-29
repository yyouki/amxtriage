# Registro de cambios

**Idioma / Bahasa / Language:** [English](CHANGELOG.md) · [Bahasa Indonesia](CHANGELOG.id.md) · [Español](CHANGELOG.es.md)

Este registro resume cambios visibles para los usuarios. No significa que se haya publicado una versión estable.

## Sin publicar

- Se añadió una interfaz de escritorio opcional con Tkinter mediante `amxtriage gui`. Los principiantes pueden elegir un registro local, una carpeta de código Pawn opcional, el idioma del informe en inglés/indonesio/español y guardar el resultado.
- Se amplió CI para probar Python 3.10–3.13 en Ubuntu y Python 3.12 en Windows y macOS. Se añadieron opciones de compartición para la rotación de registros en Windows y salida de texto LF consistente; las pruebas de métricas del host solo se ejecutan en Linux.
- Se añadieron entrypoints Pawn separados para SA-MP y open.mp. CI compila SA-MP con Pawn compiler v3.10.10 y `samp-stdlib` fijado, y open.mp con compiler v3.10.11 y `omp-stdlib` fijado.
- Se añadieron versiones en indonesio y español de la guía de plataformas/publicación y la política de seguridad, junto con una guía de publicación, soporte de plataformas y configuración del repositorio.
- Se actualizaron los metadatos del paquete para describir la CLI y la GUI opcional.

### Limitaciones conocidas

- El bridge Pawn compila en CI, pero la entrega real de alertas dentro del juego aún debe probarse en un servidor staging SA-MP/open.mp.
- No se incluye un adaptador automático de API DDoS/proveedor ni un anti-cheat de servidor. Los proveedores no comparten una API de gestión universal; cada adaptador debe validarse por separado y requerir activación explícita.
- No se distribuye una aplicación nativa Android o iOS. La GUI es para equipos de escritorio con Tkinter.
- La compatibilidad del compilador solo se verifica con las toolchains indicadas en CI, no con todas las versiones antiguas o futuras de Pawn.
