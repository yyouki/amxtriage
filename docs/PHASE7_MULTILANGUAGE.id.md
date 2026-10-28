# amxtriage — Diagnostik multi-bahasa dan operasi server yang aman

**Bahasa / Language / Idioma:** [English](PHASE7_MULTILANGUAGE.md) · [Bahasa Indonesia](PHASE7_MULTILANGUAGE.id.md) · [Español](PHASE7_MULTILANGUAGE.es.md)

**Status:** 28 Oktober 2026. Ini adalah peta jalan, bukan klaim bahwa semua fitur sudah tersedia. Fitur baru dianggap selesai jika sudah diimplementasikan dan tes relevannya lulus.

## Yang sudah tersedia

- CLI Python 3.10+ untuk menganalisis log SA-MP/open.mp: runtime error AMX, crash, dan callback lambat yang dikenali.
- Perintah analisis, pemantauan log yang bertambah, baseline, konteks source, dan rekomendasi berbasis aturan secara offline.
- Perintah `diagnose` mengenali format umum keluaran compiler/linter Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go, dan Rust. Format/versi tool belum semuanya tercakup; compiler tidak dijalankan.
- Label laporan mendukung English (`en`), Bahasa Indonesia (`id`), dan Español (`es`). Dokumentasi utama tersedia dalam tiga bahasa.
- Mode analisis/watch/preview secara default hanya membaca file lokal, tidak memulai koneksi jaringan, dan tidak mengubah source. Hanya perintah `patch-apply` eksplisit yang dapat mengedit satu file Pawn yang telah ditinjau.

## Status target fitur

| Fitur | Status |
|---|---|
| Analisis log SA-MP/open.mp | Dasar tersedia; format dari server nyata masih perlu diverifikasi lebih luas |
| CI, paket, dan pemeriksaan keselamatan | Tes lintas Python, pemeriksaan statis, packaging, serta kompilasi bridge Pawn lulus di GitHub Actions; perilaku runtime game tetap menunggu staging test |
| Diagnostik compiler multi-bahasa | Parser awal dan tes format umum tersedia; cakupan versi belum lengkap |
| Lokalisasi CLI dan Markdown | Label laporan dan dokumentasi tersedia dalam en/id/es; sebagian bantuan dan rekomendasi detail masih English |
| Katalog kompatibilitas plugin/dependensi | Sembilan entri berbukti: lima component open.mp, dua plugin legacy open.mp, satu Streamer Plugin `v2.9.6` untuk SA-MP, serta satu `sampvoice` `unknown`; filter server/status/versi/OS/arsitektur/jenis tersedia. Metadata kosong tidak dianggap kompatibel |
| Notifikasi in-game untuk admin/owner | Ekspor JSONL/`--alert-pawn-file`, source filterscript Pawn, dan kompilasi CI tersedia; pengiriman chat pada staging server belum diverifikasi |
| Mitigasi DDoS jaringan dan integrasi anti-cheat server-side | Belum dibuat |
| Patch, validasi compiler/test, dan rollback | Preview Pawn yang sempit ditambah apply eksplisit dengan hash yang dikonfirmasi, checkpoint privat, compiler lokal tepercaya, test runner terpilih atau `--compile-only`, batas waktu/output, dan rollback bersyarat; tes gameplay masih eksternal |

Dokumen bukan implementasi. Progres harus dihitung dari fitur dan kriteria penerimaan yang sudah diuji.

## Teknologi dan arsitektur

Pertahankan inti Python selama mudah dirawat dan cukup cepat. CLI ini tidak membutuhkan kompilasi native untuk berjalan; GitHub Actions dipakai untuk tes dan packaging. Pertimbangkan Rust hanya jika profiling membuktikan masalah performa atau ada kebutuhan binary native mandiri.

Tambahkan komponen secara bertahap:

- `core/`: model diagnostik, aturan keamanan berkas, dan orkestrasi.
- `adapters/<language>/`: parser khusus bahasa beserta fixture dari tool nyata.
- `catalog/`: data versi server, plugin, component, include, compiler, dan dependensi.
- `locales/`: terjemahan antarmuka. ID diagnostik, kunci JSON, exit code, dan identifier resmi harus tetap stabil.
- `fixes/`: diff, validasi, checkpoint, dan rollback.
- `integrations/`: jalur pengiriman alert yang eksplisit dan dapat dites terpisah.

Syntax tree bukan compiler dan tidak membuktikan kebenaran semantik. Tambahkan parser hanya saat ada kebutuhan dan fixture uji.

## Pilihan bahasa

Pilihan dokumentasi saat ini: English (`en`), Bahasa Indonesia (`id`), dan Español (`es`). Bahasa tambahan baru ditambahkan setelah terjemahan dan tes kelengkapan locale tersedia.

Terjemahkan bantuan CLI, error yang dibuat amxtriage, dan rekomendasi. Jangan menerjemahkan teks asli log/compiler, source code, nama file, nama plugin/native, kode diagnostik, atau kunci JSON. Skema JSON harus sama untuk semua bahasa agar otomatisasi tidak rusak. Jika terjemahan tidak ada, fallback harus didokumentasikan dan diuji.

## Katalog kompatibilitas plugin/dependensi

Setiap entri harus memuat URL proyek kanonis, URL rilis/download resmi, sumber bukti dan tanggal pemeriksaan, versi, target server SA-MP/open.mp, OS, arsitektur CPU, ABI/bitness bila berlaku, dependensi, jenis pemasangan (`plugin` atau `component`), serta status `verified`, `documented`, `unknown`, atau `incompatible`.

Link download bukan bukti kompatibilitas. Jangan mengarang link, mengunduh/menjalankan binary pihak ketiga secara otomatis, atau menyebut versi yang belum diketahui sebagai kompatibel. Perintah offline `amxtriage catalog` mencatat sembilan entri: lima rilis component open.mp yang terdokumentasi, dua plugin legacy yang tercantum dalam panduan open.mp (`rustext` v2.0.11 build `nomemhack` dan `keylistener` 1.1.2-pr), satu Streamer Plugin `v2.9.6` untuk SA-MP yang berstatus `documented` berdasarkan sumber upstream, serta satu rilis `sampvoice` lebih baru yang ditandai `unknown` karena tidak tercantum pada panduan yang dikutip. Metadata dependensi hanya diisi jika bukti yang dikutip menetapkannya; daftar kosong bukan bukti tidak ada dependensi. Matriks OS/versi server kosong bila sumber tidak menyebutkannya, dan tidak ada entri yang sudah diverifikasi runtime oleh amxtriage. Validator katalog juga menolak tanggal nonkanonis/di luar snapshot, nilai matriks kosong, serta status `verified` tanpa bukti uji runtime eksplisit dan field server/platform/arsitektur. Lihat juga [konfigurasi open.mp](https://open.mp/docs/server/config.json). Jika bukti kedaluwarsa atau bertentangan, tandai `unknown` dan jelaskan alasannya.

## Pemantauan ringan dan keamanan

Mode selalu aktif harus berupa proses/service yang terlihat, terdokumentasi, dan diaktifkan secara eksplisit pemilik server—bukan virus tersembunyi atau program yang menyebar. Jangan menyuntikkan kode ke proses game, memanipulasi memori, menghindari administrator, mengubah firewall diam-diam, atau menjalankan perintah dari teks log.

Target kinerja harus diukur, bukan dijanjikan:

- Pantau hanya file terpilih; batasi ukuran input/baris, interval polling, dan memori.
- Deduplicasi error berulang dan pakai cooldown per tanda tangan agar alert tidak membanjiri admin.
- Gunakan antrean berbatas dan backpressure; overload tidak boleh menahan game loop.
- Jaringan nonaktif secara default. Transport jarak jauh harus opt-in, terdokumentasi, terautentikasi, dan dibatasi laju.
- Gunakan izin minimum; jangan kumpulkan password atau data pemain yang tidak diperlukan.
- Ukur CPU, RAM, disk I/O, dan latensi alert pada log realistis. Tidak ada software yang dapat menjamin nol overhead atau ping selalu sama untuk semua server.

## Batas DDoS dan anti-cheat

Analisis log dapat mendeteksi gejala, tetapi tidak bisa menghentikan DDoS volumetrik sendirian. Mitigasi memerlukan perlindungan jaringan/hosting yang sesuai, seperti filtering upstream, perlindungan provider, kebijakan firewall/UDP, dan kapasitas yang cukup. Jangan mengklaim perlindungan DDoS hanya karena log dipantau.

Anti-cheat harus memvalidasi aturan game dan kejadian di sisi server. Heuristik dapat salah mendeteksi. Jangan auto-ban hanya dari satu sinyal lemah; gunakan tingkat keyakinan, audit, ambang yang dapat dikonfigurasi, dan peninjauan/pembatalan. Default monitor adalah read-only sampai pemilik mengaktifkan mitigasi yang terdokumentasi.

## Format notifikasi chat admin/owner

Skema event JSONL dan protokol `--alert-pawn-file FILE` sudah diimplementasikan. Filterscript opsional tersedia di [`integrations/pawn/amxtriage_bridge.pwn`](../integrations/pawn/amxtriage_bridge.pwn); bridge memeriksa record lokal, mengirim notifikasi hanya kepada admin yang terautentikasi RCON secara default, dan menerapkan warna path merah/baris biru. Kompilasi bridge lulus di GitHub Actions dengan versi compiler dan standard library yang dipatok. Lihat [panduan instalasi bridge](../integrations/pawn/README.md). **Pengiriman in-game end-to-end belum diuji di server staging SA-MP/open.mp nyata**, sehingga kompatibilitas runtime, izin file, rotasi log, dan dampak resource/ping masih belum terverifikasi.

Contoh konseptual: `[AMXTRIAGE] [HIGH] gamemodes/rp.pwn:42 — Array index out of bounds`

- Prefix, teks pesan, label tingkat, cooldown, dan penerima admin/owner dapat dikonfigurasi.
- Path file dan nomor baris harus diambil dari diagnostik terstruktur; template tidak boleh menimpa keduanya. Template hanya boleh memilih menampilkan/menyembunyikan nilai tetap itu.
- Warna target: path file merah dan nomor baris biru, memakai format warna API server yang benar. Tag warna dari log tidak tepercaya tidak boleh diproses sebagai markup.
- Hanya kirim ke admin terotorisasi; bersihkan newline/control characters, deduplikasi, dan rate-limit. Jangan kirim data pribadi pemain atau argumen backtrace secara default.
- Utamakan transport lokal dengan izin terbatas. RCON jarak jauh, jika didukung nanti, harus opt-in dan kredensialnya tidak boleh muncul pada argumen perintah, output, log, atau repository.
- Kegagalan pengiriman alert tidak boleh menghentikan server atau pembaca log.

## Mode perbaikan aman

Mode target: `off` (diagnostik saja), `suggest` (saran), `patch` (buat unified diff tanpa mengedit source), dan `apply` (hanya setelah persetujuan pemilik).

Setiap patch harus tetap di root proyek, menolak symlink/path escape, memastikan file tidak berubah sejak dianalisis, membuat checkpoint, dan menampilkan diff. `patch-apply` memerlukan hash source/patch yang sudah ditinjau dan compiler Pawn lokal tepercaya. Operator wajib memilih `--test-executable` dengan argumen literal berulang `--test-arg`, atau secara eksplisit memakai `--compile-only`; proses dijalankan tanpa shell dan dibatasi waktu/output. Jika validasi gagal, file asli dipulihkan hanya selama target masih identik dengan patch yang diterapkan. Jika runner mengubah source, rollback diblokir agar perubahan eksternal tidak ditimpa; checkpoint dipertahankan. Karena test runner bisa memiliki efek samping di workspace, gunakan hanya perintah yang dipercaya. Jangan instal plugin atau jalankan perintah dari log/saran secara otomatis.

Compiler sukses tidak menjamin gameplay benar. CI juga menjalankan smoke test terisolasi dengan compiler Pawn v3.10.10 yang dipatok: menangkap diagnostik compiler nyata, memastikan preview tidak mengubah source, menerapkan hash yang ditinjau hanya di direktori sementara, lalu memvalidasi hasil dengan compiler yang sama. Ini hanya menguji satu aturan, bukan kebenaran gameplay. Perlu regression fixture, startup check, dan staging test. Jika error baru muncul, simpan log dan snapshot sebelumnya alih-alih terus menerapkan perbaikan spekulatif. Tidak ada proses jujur yang dapat menjamin “100% benar setiap saat”; targetnya bukti, reproduksibilitas, dan rollback aman.

## Urutan implementasi

1. Jaga agar CI lintas versi Python, lint, format, type check, build paket, dan smoke test CLI tetap lulus; uji resource katalog dari wheel terinstal.
2. Stabilkan parser dan kontrak adapter serta fixture regresi.
3. Tambahkan adapter compiler Pawn dengan fixture tool resmi.
4. Lengkapi en/id/es dan tes kelengkapan terjemahan serta skema JSON.
5. Perluas katalog plugin/dependensi hanya berdasarkan sumber resmi; tambah pemeriksaan entri yang kedaluwarsa.
6. Uji bridge Pawn yang sudah dikompilasi pada server staging SA-MP/open.mp: verifikasi chat, filter admin RCON, warna merah/biru, izin file bersama, startup/rotasi/truncation, dan latensi alert. Tes kompilasi CI tidak sama dengan verifikasi runtime.
7. Tambahkan bahasa lain hanya dengan fixture nyata dan toolchain validasi.
8. Buat mode patch terlebih dahulu, lalu apply opt-in dengan checkpoint, compiler/test, dan rollback.
9. Tambahkan integrasi DDoS/anti-cheat hanya setelah interface yang didukung dan review keamanan tersedia.

CI adalah gerbang pemeriksaan, bukan jaminan. Jangan tandai milestone selesai sampai job dan tes perilakunya lulus.
