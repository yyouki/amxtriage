# amxtriage — Analisis log server SA-MP/open.mp

**Bahasa:** [English](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)  
**Peta jalan:** [Diagnostik multi-bahasa dan perbaikan aman](PHASE7_MULTILANGUAGE.id.md)

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
amxtriage catalog --server open.mp
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

## Katalog kompatibilitas plugin/component

Katalog lokal menampilkan proyek dan rilis yang tercantum pada sumber resmi, target server, lokasi instalasi, tanggal pemeriksaan, serta status bukti. Contoh:

```bash
amxtriage catalog
amxtriage catalog --server open.mp
amxtriage catalog --server open.mp --format markdown -o katalog-plugin.md
amxtriage plugins --format json -o katalog-plugin.json
```

Status `documented` berarti rilis tercantum pada dokumentasi upstream; status ini bukan bukti uji runtime. Katalog saat ini berisi beberapa component open.mp dari panduan instalasi resmi. Kolom versi/platform yang kosong berarti sumber tidak menentukannya. Perintah ini offline, tidak mengunduh binary, dan tidak melakukan pemasangan otomatis.

## Alert lokal dan notifikasi chat admin

Untuk mengekspor event terstruktur tanpa integrasi game, gunakan JSONL:

```bash
amxtriage watch server_log.txt --alert-jsonl ./scriptfiles/amxtriage-alerts.jsonl
```

Untuk mengirim notifikasi melalui filterscript Pawn opsional, gunakan file protokol lokal:

```bash
amxtriage watch server_log.txt --alert-pawn-file ./scriptfiles/amxtriage-alerts.txt
```

Source filterscript: [`amxtriage_bridge.pwn`](../integrations/pawn/amxtriage_bridge.pwn). Panduan instalasi: [integrations/pawn/README.md](../integrations/pawn/README.md). Filterscript harus dikompilasi dan dimuat secara eksplisit oleh pemilik server; amxtriage tidak mengubah konfigurasi server otomatis.

Bridge default hanya mengirim ke admin yang terautentikasi RCON, memeriksa maksimal lima record setiap detik, dan menampilkan path file dengan warna merah serta nomor baris dengan warna biru. Field lokasi diambil dari record diagnostik terstruktur, bukan dari template pesan yang dapat diubah. Jalankan watcher dan server dengan izin file yang sesuai; pada POSIX, file alert baru dibuat dengan mode `0600`, jadi menjalankan keduanya menggunakan akun OS yang sama biasanya paling mudah.

**Status pengujian:** source Pawn berhasil dikompilasi di GitHub Actions dengan compiler dan include yang dipatok. Pengiriman pesan belum diuji end-to-end pada server staging SA-MP/open.mp nyata. Kompilasi tidak membuktikan kompatibilitas runtime, nor ping tidak berubah. Bridge ini hanya saluran pemberitahuan diagnostik—bukan anti-cheat atau mitigasi DDoS.

## Batas kemampuan dan keamanan

Versi saat ini membaca file lokal, tidak memulai koneksi jaringan, dan tidak mengubah source code. Rekomendasi bersifat saran, bukan perbaikan otomatis.

Saat ini amxtriage **bukan** pelindung DDoS atau anti-cheat dan belum memiliki mode patch/apply otomatis. Ekspor alert JSONL serta source bridge Pawn sudah tersedia dan bridge berhasil dikompilasi di CI, tetapi pengiriman chat in-game belum diverifikasi pada server staging nyata. Pemantauan log dapat membantu melihat gejala; penghentian DDoS memerlukan mitigasi jaringan/hosting. Sistem anti-cheat harus divalidasi di sisi server dan menghindari ban otomatis berdasarkan satu indikasi lemah.

Lihat [roadmap](PHASE7_MULTILANGUAGE.id.md) dan [status progres](PROGRESS.md) untuk rincian batas kemampuan dan tahapan lanjutan.
