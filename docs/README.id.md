# amxtriage — Analisis log server SA-MP/open.mp

**Bahasa:** [English](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)  
**Peta jalan:** [Diagnostik multi-bahasa dan perbaikan aman](PHASE7_MULTILANGUAGE.id.md)  
**Platform/rilis:** [Matriks dukungan dan batasan host](RELEASE_AND_PLATFORM_SUPPORT.id.md)  
**Catatan perubahan:** [English](../CHANGELOG.md) · [Bahasa Indonesia](../CHANGELOG.id.md) · [Español](../CHANGELOG.es.md)  
**Kontribusi:** [Panduan pemula](../CONTRIBUTING.md) · **Keamanan:** [Pelaporan kerentanan](../SECURITY.md)

amxtriage adalah alat CLI Python untuk merangkum masalah yang tercatat di log SA-MP/open.mp: AMX runtime error, crash, dan callback lambat yang dikenali dari format log yang didukung. Alat ini membantu menemukan pola error berulang serta lokasi file/baris kode jika informasi tersebut tersedia.

## Antarmuka desktop untuk pemula

Setelah instalasi, jalankan:

```bash
amxtriage gui
```

Pilih file log, opsional folder source Pawn untuk menampilkan konteks kode, pilih English/Bahasa Indonesia/Spanyol, lalu simpan laporan teks. GUI memakai inti analisis yang sama dengan CLI dan tidak mengubah log. Tkinter mungkin perlu dipasang terpisah pada instalasi Linux minimal. Ini UI desktop Windows/macOS/Linux, bukan aplikasi native Android/iOS.

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

Snapshot katalog memiliki sembilan entri: lima rilis component open.mp yang terdokumentasi, dua plugin legacy open.mp (`rustext` v2.0.11 build `nomemhack` dan `keylistener` 1.1.2-pr), Streamer Plugin SA-MP `v2.9.6` yang didokumentasikan upstream, dan satu rilis `sampvoice` lebih baru berstatus `unknown` karena tidak tercantum pada panduan yang dikutip. Setiap entri memuat link proyek/rilis, lokasi instalasi, status, sumber bukti beserta tanggal, dan metadata dependensi. Status `documented` bukan bukti uji runtime. Kolom versi/platform yang kosong berarti sumber tidak menentukannya. Daftar dependensi kosong berarti katalog ini belum menemukan dependensi yang ditetapkan oleh bukti yang dikutip—bukan jaminan bahwa tidak ada dependensi. Perintah ini offline; tidak memeriksa rilis secara langsung, tidak mengunduh binary, dan tidak melakukan pemasangan otomatis.

## Alert lokal dan notifikasi chat admin

Untuk mengekspor event terstruktur tanpa integrasi game, gunakan JSONL:

```bash
amxtriage watch server_log.txt --alert-jsonl ./scriptfiles/amxtriage-alerts.jsonl
```

Untuk mengirim notifikasi melalui filterscript Pawn opsional, gunakan file protokol lokal:

```bash
amxtriage watch server_log.txt --alert-pawn-file ./scriptfiles/amxtriage-alerts.txt
```

Source filterscript: [`amxtriage_bridge.pwn`](../integrations/pawn/amxtriage_bridge.pwn). Panduan instalasi dan uji staging manual: [integrations/pawn/README.md](../integrations/pawn/README.md); helper [`scripts/staging_bridge_probe.py`](../scripts/staging_bridge_probe.py) default-nya dry-run dan memerlukan `--send --confirm-staging` untuk menambahkan record sintetis. Filterscript harus dikompilasi dan dimuat secara eksplisit oleh pemilik server; amxtriage tidak mengubah konfigurasi server otomatis.

Bridge default hanya mengirim ke admin yang terautentikasi RCON, memeriksa maksimal lima record setiap detik, dan menampilkan path file dengan warna merah serta nomor baris dengan warna biru. Field lokasi diambil dari record diagnostik terstruktur, bukan dari template pesan yang dapat diubah. Jalankan watcher dan server dengan izin file yang sesuai; pada POSIX, file alert baru dibuat dengan mode `0600`, jadi menjalankan keduanya menggunakan akun OS yang sama biasanya paling mudah.

**Status pengujian:** source Pawn berhasil dikompilasi di GitHub Actions dengan compiler dan include yang dipatok. Pengiriman pesan belum diuji end-to-end pada server staging SA-MP/open.mp nyata. Kompilasi tidak membuktikan kompatibilitas runtime atau bahwa ping tidak berubah. Bridge ini hanya saluran pemberitahuan diagnostik—bukan anti-cheat atau mitigasi DDoS.

## Monitoring metrik lokal (opt-in, Linux)

Tambahkan opsi berikut bila ingin menyimpan metrik host dan proses watcher secara lokal:

```bash
amxtriage watch server_log.txt --alert-pawn-file ./scriptfiles/amxtriage-alerts.txt --metrics-jsonl ./amxtriage-metrics.jsonl --metrics-interval 5
```

Metrik mencakup CPU/RAM host, CPU/RSS proses amxtriage, I/O disk yang terlihat, serta waktu pemrosesan ekspor alert lokal. File metrik wajib terpisah dari log dan file alert. Waktu ekspor bukan latensi chat in-game; CI hanya menjalankan benchmark sintetis tiga alert, bukan mengukur dampak server game atau ping pemain. Backend ini saat ini hanya mendukung Linux.

## Pratinjau patch aman (hanya diff)

Perintah `patch-preview` membuat diff untuk satu kasus Pawn yang sempit: error compiler `001` menyatakan titik koma hilang tepat sebelum `return`, dan baris sebelumnya merupakan assignment/deklarasi sederhana. File source harus bisa ditemukan secara unik dan aman di dalam `--source-dir`.

```bash
amxtriage patch-preview compile.log --source-dir . --format unified
amxtriage patch-preview compile.log --source-dir . --format json -o pratinjau-patch.json
```

Ini **bukan** perbaikan otomatis untuk semua error. Source tidak diubah, patch tidak diterapkan, dependensi tidak diunduh, dan compiler tidak dijalankan. Kasus yang ambigu atau belum didukung akan ditolak. Format `unified` menerima satu log compiler setelah ekspansi wildcard dan hanya mencetak diff; jika tidak ada kandidat aman, alasan dikirim ke stderr dan proses keluar dengan status `3`. Tinjau diff, kompilasi dengan compiler Pawn resmi, lalu jalankan tes regresi/gameplay sebelum menggunakannya.

## Terapkan patch dengan persetujuan eksplisit

`patch-apply`/`fix-apply` hanya mendukung aturan Pawn yang sama dan memerlukan hash source serta patch yang sudah ditinjau. Wajib memilih compiler Pawn lokal tepercaya dan test/linter tepercaya (`--test-executable` beserta `--test-arg`) atau menyatakan `--compile-only`. Tool membuat checkpoint privat, menyinkronkan entri direktorinya sebelum mengganti source, menjalankan validasi tanpa shell dengan batas waktu/output, dan melakukan rollback hanya jika target masih sama dengan patch yang diterapkan. Jika ada perubahan eksternal, rollback diblokir dan checkpoint dipertahankan. Tes CI memakai compiler Pawn v3.10.10 untuk satu aturan saja; ini tidak membuktikan logika gameplay benar.

## Batas kemampuan dan keamanan

Mode analisis/watch/katalog/preview normal bekerja offline dan tidak menjalankan program anak atau mengubah source. Metrik Linux bersifat opt-in. Hanya `patch-apply` eksplisit yang dapat mengubah satu perbaikan Pawn setelah hash konfirmasi, checkpoint, dan validasi yang dipilih operator; compiler/test lokal tepercaya dijalankan tanpa shell. Rekomendasi tetap bersifat saran, bukan jaminan perbaikan benar.

Saat ini amxtriage **bukan** pelindung DDoS atau anti-cheat; `patch-apply` tersedia sebagai jalur opt-in yang sempit dan memerlukan persetujuan eksplisit, bukan auto-fix umum. Ekspor alert JSONL serta source bridge Pawn sudah tersedia dan bridge berhasil dikompilasi di CI, tetapi pengiriman chat in-game belum diverifikasi pada server staging nyata. Pemantauan log dapat membantu melihat gejala; penghentian DDoS memerlukan mitigasi jaringan/hosting. Sistem anti-cheat harus divalidasi di sisi server dan menghindari ban otomatis berdasarkan satu indikasi lemah.

Lihat [roadmap](PHASE7_MULTILANGUAGE.id.md) dan [status progres](PROGRESS.md) untuk rincian batas kemampuan dan tahapan lanjutan.
