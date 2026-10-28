# Status Proyek amxtriage

**Snapshot:** 28 Oktober 2026  
**Branch target:** `main`  
**Kode yang diaudit:** `03cc320c3dd52ea62dd0b9938f9c4bfcb98015b8`  
**CI terverifikasi:** [Run 40655207311 lulus](https://github.com/yyouki/amxtriage/actions/runs/40655207311) pada commit `03cc320`. Keenam job lulus: tes pada Python 3.10, 3.11, 3.12, dan 3.13; Ruff lint/format, mypy strict, wheel/sdist, validasi metadata, smoke test CLI/katalog, serta kompilasi filterscript Pawn. CI tidak menguji pengiriman chat pada server game live.

**Bahasa / Language / Idioma:** [English README](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)

## Progres keseluruhan

**Estimasi berbobot: 62,5% dari target produk penuh (62,5/100; dibulatkan 63%).** Ini estimasi perencanaan berdasarkan implementasi dan tes yang tersedia, bukan jaminan akurasi atau bukti bahwa semua integrasi telah diuji pada server nyata.

| Area | Bobot | Porsi selesai yang diperkirakan | Poin |
|---|---:|---:|---:|
| Analisis log dan hardening dasar | 20 | 90% | 18 |
| Diagnostik keluaran compiler multi-bahasa | 15 | 67% | 10 |
| Lokalisasi CLI dan dokumentasi | 10 | 70% | 7 |
| CI, pengujian lintas Python, packaging, kompilasi Pawn | 10 | 100% | 10 |
| Katalog kompatibilitas plugin/dependensi | 10 | 50% | 5 |
| Monitor dan bridge alert admin | 10 | 60% | 6 |
| Mitigasi DDoS dan integrasi anti-cheat sisi server | 15 | 0% | 0 |
| Patch preview, hash konfirmasi, validasi compiler/test, checkpoint, rollback | 10 | 65% | 6.5 |
| **Total** | **100** |  | **62,5/100 = 62,5%** |

Nilai area tetap konservatif: dokumentasi bukan implementasi, kompilasi bukan bukti pengiriman live, dan validasi compiler bukan bukti kebenaran gameplay.

## Yang sudah tersedia

- CLI Python untuk analisis log SA-MP/open.mp, pengelompokan masalah, `watch`, baseline, konteks source, dan rekomendasi offline.
- Diagnostik teks compiler/linter untuk format umum Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go, dan Rust. Ini tidak mencakup semua versi tool; perintah `diagnose` tidak menjalankan compiler.
- Label laporan dan dokumentasi English, Bahasa Indonesia, dan Español.
- Katalog offline sembilan entri: lima rilis component yang didokumentasikan open.mp, dua plugin legacy open.mp, satu rilis Streamer Plugin `v2.9.6` untuk SA-MP dengan status `documented`, dan satu versi `sampvoice` lebih baru berstatus `unknown`. Filter CLI mendukung server, status bukti, versi server yang terdokumentasi secara persis, OS/platform, arsitektur CPU, dan jenis instalasi. Nilai hanya cocok jika tercantum pada bukti katalog; field kosong tidak pernah berarti kompatibel.
- Alert JSONL dan protokol lokal `--alert-pawn-file`, template pesan terbatas, field path/baris terstruktur yang tidak dapat ditimpa template, file output lokal yang dibatasi, deduplikasi/cooldown, serta rate limit.
- Filterscript Pawn `integrations/pawn/amxtriage_bridge.pwn` yang default-nya hanya memberi chat ke admin RCON, menampilkan path merah dan nomor baris biru, dan memproses paling banyak lima record per tick. Source bridge dikompilasi dengan toolchain Pawn yang dipatok di CI. Buffer pesan chat dibatasi 143 karakter terlihat; tanda `%` dikirim literal tanpa penggandaan yang tidak perlu.
- `patch-preview`/`fix-preview` menghasilkan unified diff tanpa mengubah source untuk satu aturan sintaks Pawn berkeyakinan tinggi: compiler error `001` untuk titik koma yang hilang tepat sebelum `return`, dengan baris sebelumnya berupa assignment/deklarasi sederhana.
- `patch-apply`/`fix-apply` hanya menerapkan patch yang source-hash dan patch-hash-nya telah dikonfirmasi dari preview yang ditinjau. Ia memeriksa path/source, membuat checkpoint berizin `0600`, menyinkronkan entri direktori checkpoint sebelum mengganti source, lalu menjalankan compiler Pawn lokal tepercaya. Operator wajib memilih `--test-executable` dengan argumen literal `--test-arg`, atau secara eksplisit memilih `--compile-only`. Perintah validasi berjalan tanpa shell dengan batas waktu/output; kegagalan compiler/test mencoba rollback hanya jika target masih identik dengan patch yang diterapkan. Jika test runner mengubah target, rollback diblokir untuk menjaga perubahan eksternal. Tes memakai compiler/test stub dan tidak membuktikan kebenaran gameplay.

## Yang belum boleh diklaim selesai

- Chat alert **belum diverifikasi end-to-end pada server staging/live SA-MP/open.mp**. Kompilasi Pawn dan tes protokol lokal tidak membuktikan callback timing, ACL pada server target, izin file bersama, perilaku saat rotasi/truncation, atau dampak resource/ping.
- CPU, RAM, disk I/O, dan latency alert belum diukur pada server nyata; tidak ada klaim “nol overhead”.
- Katalog belum memiliki matriks runtime yang lengkap. Versi server, OS, arsitektur CPU/ABI, dan dependensi tetap kosong ketika sumber resmi tidak menetapkannya. Belum ada entri yang ditandai runtime-`verified` oleh amxtriage.
- `patch-apply` tidak menyediakan test suite proyek atau linter khusus secara otomatis; operator harus memilih perintah validasi lokal yang dipercaya, atau dengan sadar memilih `--compile-only`. Cakupan patch masih satu aturan Pawn. Tes stub bukan pengganti pengujian source nyata, startup check, atau staging game.
- Mitigasi DDoS jaringan/provider dan integrasi anti-cheat server-side belum dibuat. Log analyzer hanya bisa mendeteksi gejala dan tidak bisa sendiri menghentikan serangan volumetrik.

## Gerbang berikutnya

1. **Bridge:** jalankan staging test dengan versi server dan OS yang diketahui; periksa otorisasi admin, warna, path/baris, izin file, record parsial, truncation/rotasi, deduplikasi, dan latency. Sampai itu tersedia, integrasi live tetap berstatus belum diverifikasi.
2. **Katalog:** sembilan entri kini mencakup open.mp dan SA-MP. Audit ulang tanggal serta URL sumber secara berkala; isi versi server, OS/platform, arsitektur dan dependensi hanya saat bukti resmi menetapkannya. Field yang tidak terbukti harus tetap `unknown`/kosong dan tidak boleh menghasilkan klaim kompatibilitas.
3. **Patch:** perluas aturan hanya setelah fixture compiler yang nyata tersedia; tambah test/linter yang spesifik untuk tiap proyek, uji integrasi staging, dan pengujian konkurensi/interrupt untuk rollback. Runner saat ini eksplisit, tanpa shell, dibatasi waktu/output, dan sudah diuji dengan stub untuk sukses/gagal/timeout/output berlebih. Compiler/test lulus tetap bukan bukti benar secara gameplay.
4. **Monitoring:** ukur CPU/RAM/disk I/O dan latensi alert saat idle serta log sibuk di host uji.
5. **DDoS/anti-cheat:** hanya tambahkan adapter yang benar-benar didukung provider/server dan memerlukan opt-in. Jangan klaim perlindungan universal.

Gunakan `main` sesuai permintaan; jangan force-push atau mengganti perubahan yang belum diaudit. Tandai milestone selesai hanya setelah kriteria penerimaan dan tes relevan lulus.
