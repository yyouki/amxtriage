# Kebijakan keamanan

**Bahasa / Language / Idioma:** [English](../SECURITY.md) · [Bahasa Indonesia](SECURITY.id.md) · [Español](SECURITY.es.md)

## Melaporkan kerentanan

Jangan memublikasikan rahasia, langkah eksploitasi, atau log server privat dalam issue publik.

Jika pelaporan kerentanan privat diaktifkan untuk repositori ini, gunakan tab **Security**. Jika tidak tersedia, buat issue singkat yang meminta maintainer mengaktifkan jalur pelaporan privat; jangan sertakan detail eksploitasi atau kredensial pada issue tersebut.

Sertakan versi/commit yang terdampak, sistem operasi, versi Python, dan reproduksi minimal yang sudah menghapus informasi sensitif. Jangan pernah menyertakan kredensial RCON, kata sandi pemain, token akses, atau informasi pelanggan privat.

## Cakupan dan default aman

amxtriage adalah utilitas analisis log lokal dengan bridge notifikasi diagnostik opsional. Ini bukan layanan penyaring DDoS. Laporkan dugaan penanganan path yang tidak aman, eksekusi input dari log, bypass otorisasi bridge, atau perubahan source yang tidak dimaksudkan.

Dokumen ini tidak menjanjikan SLA waktu respons.
