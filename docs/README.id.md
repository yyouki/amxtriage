# amxtriage — Analisis log server SA-MP/open.mp

**Bahasa:** [English](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)  
**Peta jalan:** [Diagnostik multi-bahasa dan perbaikan aman](PHASE7_MULTILANGUAGE.md)

amxtriage adalah alat CLI Python untuk merangkum masalah yang tercatat di log SA-MP/open.mp: AMX runtime error, crash, dan callback lambat yang dikenali dari format log yang didukung. Alat ini membantu menemukan pola error berulang serta lokasi file/baris kode jika informasi tersebut tersedia.

## Fitur yang tersedia sekarang

- Analisis log teks, file `.gz`, dan input standar.
- Mengelompokkan error serupa dan menghitung frekuensinya.
- Menampilkan konteks dari file sumber Pawn jika tersedia.
- Mode `watch` untuk mengikuti log yang bertambah.
- Baseline untuk membandingkan masalah baru.
- Rekomendasi diagnostik berbasis aturan yang bekerja offline.

## Instalasi

Memerlukan Python 3.10 atau lebih baru.

```bash
python -m pip install .
amxtriage analyze server_log.txt
amxtriage watch server_log.txt --poll-interval 1
amxtriage recommend server_log.txt
```

Dari checkout tanpa instalasi:

```bash
PYTHONPATH=src python -m amxtriage analyze examples/sample_server_log.txt
```

Label laporan CLI mendukung English (`en`, default), Bahasa Indonesia (`id`), dan Español (`es`). Pilih bahasa sebelum atau sesudah subperintah:

```bash
amxtriage --language id analyze server_log.txt
amxtriage analyze server_log.txt --lang id
amxtriage recommend server_log.txt --language es
```

Terjemahan CLI masih bertahap: label dan judul laporan telah diterjemahkan, tetapi saran diagnosis yang mendetail, beberapa pesan bantuan, dan teks asli dari log/compiler dapat tetap berbahasa Inggris. Kunci JSON tetap berbahasa Inggris dan stabil agar skrip otomatisasi tidak rusak. Gunakan `amxtriage --help` atau `amxtriage <command> --help` untuk opsi lain.

## Batas kemampuan dan keamanan

Versi saat ini membaca file lokal, tidak memulai koneksi jaringan, dan tidak mengubah source code. Rekomendasi bersifat saran, bukan perbaikan otomatis.

Saat ini amxtriage **bukan** pelindung DDoS, bukan anti-cheat, belum mengirim notifikasi ke chat admin dalam game, dan belum menerapkan patch otomatis. Pemantauan log dapat membantu melihat gejala, tetapi penghentian DDoS memerlukan mitigasi jaringan/hosting. Sistem anti-cheat harus divalidasi di sisi server dan menghindari ban otomatis berdasarkan satu indikasi lemah.

Lihat [roadmap](PHASE7_MULTILANGUAGE.md) untuk rancangan integrasi notifikasi admin, pilihan bahasa, katalog kompatibilitas plugin, dan alur patch dengan validasi serta rollback.
