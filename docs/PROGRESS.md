# Status Proyek amxtriage

**Snapshot:** 28 Oktober 2026  
**Branch target:** `main`  
**Commit kode fitur yang terakhir diverifikasi:** `3d79847f4bf67fd75c40c4afb7eb08cb88cdd8bc`  
**CI:** [Run 40627116263 lulus](https://github.com/yyouki/amxtriage/actions/runs/40627116263) pada kode `3d79847`; 1.843 tes lulus pada masing-masing Python 3.10, 3.11, 3.12, dan 3.13. Ruff lint/format, mypy strict, build wheel/sdist, validasi metadata, smoke test CLI, serta kompilasi filterscript Pawn juga lulus. CI tidak menguji pengiriman chat pada server game live.

**Bahasa / Language / Idioma:** [English README](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)

## Progres keseluruhan

**Estimasi berbobot: 57% dari target produk penuh.** Ini estimasi perencanaan, bukan metrik otomatis dan bukan klaim bahwa sistem sudah teruji penuh pada server nyata. Perhitungan memakai bobot 100 poin dan menilai implementasi serta tes yang benar-benar tersedia.

| Area | Bobot | Porsi selesai yang diperkirakan | Poin |
|---|---:|---:|---:|
| Analisis log dan hardening dasar | 20 | 90% | 18 |
| Diagnostik keluaran compiler multi-bahasa | 15 | 67% | 10 |
| Lokalisasi CLI dan dokumentasi | 10 | 70% | 7 |
| CI, pengujian lintas Python, packaging, kompilasi Pawn | 10 | 100% | 10 |
| Katalog kompatibilitas plugin/dependensi | 10 | 40% | 4.0 |
| Monitor dan bridge alert admin | 10 | 60% | 6 |
| Mitigasi DDoS dan integrasi anti-cheat sisi server | 15 | 0% | 0 |
| Patch preview yang aman, validasi, rollback | 10 | 20% | 2 |
| **Total** | **100** |  | **57/100 = 57%** |

Nilai dibulatkan untuk tampilan. Persentase area bukan bukti kualitas runtime: perubahan tidak boleh menaikkan skor hanya karena file atau dokumentasi baru ditambahkan.

## Yang sudah tersedia

- CLI Python untuk analisis log SA-MP/open.mp, pengelompokan masalah, `watch`, baseline, konteks source, dan rekomendasi offline.
- Diagnostik teks compiler/linter untuk format umum Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go, dan Rust. Ini tidak mencakup semua versi tool dan perintah `diagnose` tidak menjalankan compiler.
- Label laporan dan dokumentasi English, Bahasa Indonesia, dan Español.
- Katalog offline mencatat lima rilis component yang tercantum di dokumentasi open.mp, satu rilis sampvoice yang belum dipastikan (`unknown`), serta dua plugin legacy (rustext dan keylistener) yang direkomendasikan oleh panduan migrasi resmi. Dependencies ditampilkan hanya jika bukti upstream menyebutkannya; daftar kosong bukan bukti bahwa tidak ada dependensi.
- Alert JSONL dengan template terbatas, field lokasi terstruktur yang tidak dapat ditimpa template, safe local output, dan perilaku fail-safe jika ekspor gagal.
- Opsi `watch --alert-pawn-file` dan source filterscript `integrations/pawn/amxtriage_bridge.pwn`. Bridge default hanya mengirim ke admin RCON, membatasi pemrosesan menjadi lima record per detik, serta menampilkan path merah dan nomor baris biru.
- GitHub Actions menjalankan tes Python 3.10–3.13, pemeriksaan kualitas/paket, dan kompilasi Pawn dengan toolchain yang dipatok. Source bridge berhasil dikompilasi dalam CI.
- Perintah `patch-preview` (alias `fix-preview`) yang hanya menghasilkan unified diff untuk satu kasus Pawn berkeyakinan tinggi: compiler error `001` menyatakan titik koma hilang tepat sebelum `return`, dengan baris sebelumnya berupa assignment/deklarasi sederhana. Kasus ambigu atau tidak aman ditolak; source tidak diedit dan compiler tidak dijalankan.

## Yang belum boleh diklaim selesai

- Chat alert **belum diverifikasi end-to-end pada server staging/live SA-MP/open.mp**. Kompilasi Pawn tidak membuktikan izin file, callback timing, role/ACL, warna, rotasi/truncation, atau dampak resource/ping di server nyata.
- Dampak CPU/RAM/disk I/O dan ping belum diukur secara benchmark pada server nyata; tidak ada klaim “nol overhead”.
- Katalog kompatibilitas masih terbatas: lima rilis component open.mp terdokumentasi, dua plugin legacy terdokumentasi, dan satu rilis sampvoice berstatus `unknown`. Matriks runtime untuk versi server, OS, arsitektur, ABI, dan dependensi masih belum lengkap.
- Mitigasi DDoS jaringan/provider dan integrasi anti-cheat server-side belum dibuat.
- Mode `apply` dengan checkpoint, validasi compiler/tes, bounded repair loop, dan rollback belum dibuat. `patch-preview` saat ini hanya mendukung satu aturan sintaks Pawn; diff yang dihasilkan masih perlu ditinjau dan diuji secara manual.

## Gerbang untuk milestone berikutnya

1. Uji bridge pada server staging dengan versi server dan OS yang diketahui; periksa filter admin, warna, path/baris, izin file bersama, alert ganda, record belum lengkap, rotasi/truncation, dan latensi alert.
2. Ukur penggunaan CPU/RAM/disk I/O dan latency alert saat idle serta saat log sibuk; laporkan angka hasil ukur, bukan janji.
3. Perluas katalog hanya bila proyek, rilis, versi, dan kompatibilitas memiliki bukti resmi; jika bukti kurang, gunakan `unknown`.
4. Perluas aturan `patch-preview` hanya jika ada fixture compiler yang kuat; setelah itu rancang apply opt-in dengan checkpoint, compiler/test resmi, pemeriksaan regresi, batas percobaan, dan rollback. Jangan menganggap preview saat ini sebagai auto-fix.
5. Untuk DDoS/anti-cheat, integrasikan hanya provider atau API yang benar-benar didukung. Jangan mengklaim perlindungan universal dari analisis log.

Gunakan branch `main` sesuai permintaan proyek, jangan force-push atau membuang perubahan yang belum diperiksa, dan tandai fitur selesai hanya setelah kriteria penerimaan serta tes relevan lulus.
