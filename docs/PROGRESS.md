# Status Proyek amxtriage

**Snapshot:** 29 Oktober 2026  
**Branch target:** `main`  
**Kode yang diaudit:** `ef0607c6565cd9e7b17104f5bdef08fb099dbf39`  
**CI terverifikasi:** [Run 40854311765 lulus](https://github.com/yyouki/amxtriage/actions/runs/40854311765) pada commit `ef0607c`. Delapan job lulus: 1.899 tes pada masing-masing Python 3.10, 3.11, 3.12, dan 3.13 di Ubuntu; Python 3.12 di macOS: 1.883 lulus dan 16 dilewati; Python 3.12 di Windows: 1.798 lulus dan 101 dilewati (termasuk tes khusus POSIX); pemeriksaan Ruff, mypy strict, build wheel/sdist, validasi metadata dan smoke test paket; serta kompilasi bridge SA-MP dan open.mp. CI tidak menguji pengiriman chat pada server game live atau dampaknya terhadap ping pemain.

**Bahasa / Language / Idioma:** [English README](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)

## Progres keseluruhan

**Estimasi berbobot: 65,0% dari target produk penuh (65,0/100).** Ini estimasi perencanaan berdasarkan implementasi dan tes yang tersedia, bukan jaminan akurasi atau bukti bahwa semua integrasi telah diuji pada server nyata.

| Area | Bobot | Porsi selesai yang diperkirakan | Poin |
|---|---:|---:|---:|
| Analisis log dan hardening dasar | 20 | 90% | 18 |
| Diagnostik keluaran compiler multi-bahasa | 15 | 67% | 10 |
| Lokalisasi CLI, GUI desktop, dan dokumentasi | 10 | 80% | 8 |
| CI, pengujian lintas Python, packaging, kompilasi Pawn | 10 | 100% | 10 |
| Katalog kompatibilitas plugin/dependensi | 10 | 50% | 5 |
| Monitor dan bridge alert admin | 10 | 70% | 7 |
| Mitigasi DDoS dan integrasi anti-cheat sisi server | 15 | 0% | 0 |
| Patch preview, hash konfirmasi, validasi compiler/test, checkpoint, rollback | 10 | 70% | 7.0 |
| **Total** | **100** |  | **65,0/100 = 65,0%** |

Nilai area tetap konservatif: dokumentasi bukan implementasi, kompilasi bukan bukti pengiriman live, dan validasi compiler bukan bukti kebenaran gameplay.

## Yang sudah tersedia

- CLI Python untuk analisis log SA-MP/open.mp, pengelompokan masalah, `watch`, baseline, konteks source, dan rekomendasi offline. CI menguji Python 3.10–3.13 di Ubuntu serta Python 3.12 pada Windows dan macOS.
- Diagnostik teks compiler/linter untuk format umum Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go, dan Rust. Ini tidak mencakup semua versi tool; perintah `diagnose` tidak menjalankan compiler.
- Label laporan dan dokumentasi English, Bahasa Indonesia, dan Español.
- Katalog offline sembilan entri: lima rilis component yang didokumentasikan open.mp, dua plugin legacy open.mp, satu rilis Streamer Plugin `v2.9.6` untuk SA-MP dengan status `documented`, dan satu versi `sampvoice` lebih baru berstatus `unknown`. Filter CLI mendukung server, status bukti, versi server yang terdokumentasi secara persis, OS/platform, arsitektur CPU, dan jenis instalasi. Nilai hanya cocok jika tercantum pada bukti katalog; field kosong tidak pernah berarti kompatibel. Validator menolak tanggal nonkanonis/di luar snapshot, nilai matriks kosong, dan status `verified` tanpa matriks server/platform/arsitektur serta pernyataan bukti runtime yang eksplisit.
- Alert JSONL dan protokol lokal `--alert-pawn-file`, template pesan terbatas, field path/baris terstruktur yang tidak dapat ditimpa template, file output lokal yang dibatasi, deduplikasi/cooldown, serta rate limit.
- Bridge Pawn mempunyai entrypoint khusus SA-MP (`integrations/pawn/amxtriage_bridge.pwn`) dan open.mp (`integrations/pawn/amxtriage_bridge_openmp.pwn`) dengan protokol/implementasi bersama. CI mengompilasi SA-MP menggunakan Pawn compiler v3.10.10 dengan `samp-stdlib` yang dipatok dan open.mp menggunakan compiler v3.10.11 dengan `omp-stdlib` yang dipatok. Keduanya hanya teruji pada build level; pengiriman chat end-to-end tetap perlu staging test.
- GUI desktop Tkinter opsional tersedia melalui `amxtriage gui`: pilih log, folder source Pawn opsional, bahasa laporan en/id/es, lalu simpan laporan teks. UI memakai core analisis yang sama dan tidak mengubah log; native Android/iOS belum tersedia.
- `scripts/staging_bridge_probe.py` menambahkan satu record sintetis berlabel `STAGING-PROBE` untuk membantu operator mengecek pengiriman chat secara visual. Default-nya dry-run dan penulisan memerlukan `--send --confirm-staging`; script tidak dapat mengamati chat, jadi status end-to-end tetap belum terverifikasi sampai operator melakukan pemeriksaan pada server staging nyata.
- Monitoring opt-in Linux melalui `watch --metrics-jsonl FILE --metrics-interval N` menulis JSONL CPU host, memori host, CPU/RSS proses amxtriage, laju I/O block-device yang terlihat, dan waktu pemrosesan ekspor alert lokal. Pengambilan sampel default nonaktif; data tidak mengukur CPU proses game atau pengiriman chat in-game.
- `scripts/benchmark_watch.py` mengukur latensi alert JSONL, CPU/RSS proses, dan I/O kernel untuk beban file sintetis lokal. CI menjalankan tiga event sintetis; hasil contoh pada runner GitHub: p95 sekitar 105 ms dan RSS sampel sekitar 25 MB. Angka ini hanya untuk runner/workload tersebut, bukan baseline server produksi atau ping pemain.
- `patch-preview`/`fix-preview` menghasilkan unified diff tanpa mengubah source untuk satu aturan sintaks Pawn berkeyakinan tinggi: compiler error `001` untuk titik koma yang hilang tepat sebelum `return`, dengan baris sebelumnya berupa assignment/deklarasi sederhana.
- `patch-apply`/`fix-apply` hanya menerapkan patch yang source-hash dan patch-hash-nya telah dikonfirmasi dari preview yang ditinjau. Ia memeriksa path/source, membuat checkpoint berizin `0600`, menyinkronkan entri direktori checkpoint sebelum mengganti source, lalu menjalankan compiler Pawn lokal tepercaya. Operator wajib memilih `--test-executable` dengan argumen literal `--test-arg`, atau secara eksplisit memilih `--compile-only`. Perintah validasi berjalan tanpa shell dengan batas waktu/output; kegagalan compiler/test mencoba rollback hanya jika target masih identik dengan patch yang diterapkan. Jika test runner mengubah target, rollback diblokir untuk menjaga perubahan eksternal. Tes unit memakai compiler/test stub, sementara CI juga menjalankan smoke test dengan compiler Pawn v3.10.10 nyata untuk satu aturan; keduanya tidak membuktikan kebenaran gameplay.

## Yang belum boleh diklaim selesai

- Chat alert **belum diverifikasi end-to-end pada server staging/live SA-MP/open.mp**. Kompilasi Pawn dan tes protokol lokal tidak membuktikan callback timing, ACL pada server target, izin file bersama, perilaku saat rotasi/truncation, atau dampak resource/ping.
- CPU, RAM, disk I/O, dan latency alert belum diukur pada server game nyata. Benchmark yang ada hanya beban sintetis lokal; tidak ada klaim “nol overhead” atau ping tanpa dampak.
- Katalog belum memiliki matriks runtime yang lengkap. Versi server, OS, arsitektur CPU/ABI, dan dependensi tetap kosong ketika sumber resmi tidak menetapkannya. Belum ada entri yang ditandai runtime-`verified` oleh amxtriage.
- `patch-apply` tidak menyediakan test suite proyek atau linter khusus secara otomatis; operator harus memilih perintah validasi lokal yang dipercaya, atau dengan sadar memilih `--compile-only`. Cakupan patch masih satu aturan Pawn. Tes stub bukan pengganti pengujian source nyata, startup check, atau staging game.
- Mitigasi DDoS jaringan/provider dan integrasi anti-cheat server-side belum dibuat. Log analyzer hanya bisa mendeteksi gejala dan tidak bisa sendiri menghentikan serangan volumetrik.

## Gerbang berikutnya

1. **Bridge:** gunakan `scripts/staging_bridge_probe.py` pada server staging setelah filterscript dan watcher aktif; periksa otorisasi admin, warna, path/baris, izin file, record parsial, truncation/rotasi, deduplikasi, dan latency. Script hanya menulis record uji; operator harus mengamati chat secara manual. Sampai itu dilakukan, integrasi live tetap berstatus belum diverifikasi.
2. **Katalog:** sembilan entri kini mencakup open.mp dan SA-MP. Audit ulang tanggal serta URL sumber secara berkala; isi versi server, OS/platform, arsitektur dan dependensi hanya saat bukti resmi menetapkannya. Field yang tidak terbukti harus tetap `unknown`/kosong dan tidak boleh menghasilkan klaim kompatibilitas.
3. **Patch:** perluas aturan hanya setelah fixture compiler yang nyata tersedia; tambah test/linter yang spesifik untuk tiap proyek, uji integrasi staging, dan pengujian konkurensi/interrupt untuk rollback. Runner saat ini eksplisit, tanpa shell, dibatasi waktu/output, dan sudah diuji dengan stub untuk sukses/gagal/timeout/output berlebih. Compiler/test lulus tetap bukan bukti benar secara gameplay.
4. **Monitoring:** ukur CPU/RAM/disk I/O dan latensi alert saat idle serta log sibuk di host uji.
5. **DDoS/anti-cheat:** tidak ada satu API mitigasi universal untuk semua host. Panduan rilis mencatat kemampuan resmi beberapa provider umum, tetapi adapter API otomatis belum diimplementasikan. Host yang tidak memiliki API publik memerlukan konfigurasi manual; jangan klaim dukungan otomatis untuk semua host. Adapter nyata harus khusus-provider, opt-in, terbatas pada resource milik operator, memiliki dry-run/audit log, dan diuji di staging. Analisis log saja tidak menghentikan DDoS volumetrik.

Gunakan `main` sesuai permintaan; jangan force-push atau mengganti perubahan yang belum diaudit. Tandai milestone selesai hanya setelah kriteria penerimaan dan tes relevan lulus.
