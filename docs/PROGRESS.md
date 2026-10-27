# Status Proyek amxtriage

**Snapshot:** 27 Oktober 2026  
**Revisi dasar yang diperiksa:** `50e2fa7d0adf369b112de762c1dacf82194d89cf`  
**CI:** Hijau pada revisi dasar ini; job tes Python 3.10–3.13, pemeriksaan kualitas, build paket, validasi metadata, dan smoke test CLI lulus.  
**Bahasa / Language / Idioma:** [English README](../README.md) · [Bahasa Indonesia](README.id.md) · [Español](README.es.md)

## Progres keseluruhan

**Estimasi berbobot: 48% dari target produk penuh.** Ini adalah estimasi proyek berdasarkan bobot milestone yang tercantum di bawah, bukan metrik otomatis atau klaim bahwa fitur berjalan pada server nyata.

| Area | Bobot | Porsi selesai yang diperkirakan | Poin |
|---|---:|---:|---:|
| Analisis log dan hardening dasar | 20 | 90% | 18 |
| Diagnostik keluaran compiler multi-bahasa | 15 | 67% | 10 |
| Lokalisasi CLI dan dokumentasi | 10 | 70% | 7 |
| CI, pengujian lintas Python, packaging | 10 | 100% | 10 |
| Katalog kompatibilitas plugin/dependensi | 10 | 0% | 0 |
| Monitor selalu aktif dan bridge chat admin | 10 | 20% | 2 |
| Mitigasi DDoS dan integrasi anti-cheat sisi server | 15 | 0% | 0 |
| Patch otomatis yang aman, validasi, rollback | 10 | 10% | 1 |
| **Total** | **100** |  | **48/100** |

Bobot dan persentase adalah estimasi perencanaan. Perbarui setelah mengubah kriteria penerimaan, tetapi jangan menaikkan angka hanya karena kode atau dokumentasi baru ditambahkan. Fitur dihitung selesai jika implementasi, tes relevan, dan batas kemampuannya sudah didokumentasikan.

## Yang sudah tersedia

- CLI Python untuk analisis log SA-MP/open.mp, pengelompokan masalah, `watch`, baseline, konteks source, serta rekomendasi offline.
- Diagnostik teks compiler/linter untuk format umum Pawn, Python, JavaScript/TypeScript, C/C++, Java, C#, Go, dan Rust; ini tidak mencakup semua versi tool dan tidak menjalankan compiler.
- Label laporan dan dokumentasi English, Bahasa Indonesia, dan Español.
- CI GitHub Actions lintas Python 3.10–3.13, lint/format/type check, build distribusi, dan smoke test instalasi.
- Peta jalan fitur tersedia dalam English, Bahasa Indonesia, dan Español.

## Yang belum boleh diklaim tersedia

- Katalog plugin/dependensi yang punya bukti kompatibilitas dan URL rilis resmi.
- Pengiriman notifikasi langsung ke chat dalam game untuk admin/owner.
- Perlindungan DDoS jaringan. Analisis log saja tidak bisa memitigasi serangan volumetrik.
- Deteksi cheat yang divalidasi di sisi server.
- Mode `patch`/`apply` yang membuat checkpoint, menjalankan compiler/test, dan rollback jika validasi gagal.
- Beban CPU/RAM dan dampak ping yang sudah diukur pada server SA-MP/open.mp nyata.

## Aturan untuk pembaruan berikutnya

1. Gunakan branch `main` sesuai arah proyek saat ini; jangan force-push atau menimpa perubahan yang tidak diperiksa.
2. Setelah setiap perbaikan, jalankan seluruh tes, lint, format, mypy, build, validasi paket, dan smoke test lewat CI. Perbaikan belum selesai sampai job terkait hijau.
3. Untuk fitur server, pisahkan unit test dari integrasi nyata. Catat versi server, OS, compiler Pawn, plugins/components, dan hasil uji staging.
4. Jangan mengklaim “100% benar setiap kali”. Jika validasi menemukan error baru, simpan reproduksi, perbaiki penyebabnya, dan jalankan kembali seluruh pemeriksaan.
5. Mode selalu aktif harus transparan dan opt-in—bukan tersembunyi, menyebar sendiri, atau menginjeksi proses game. Semua tindakan yang memblokir pemain harus nonaktif secara default dan dapat diaudit.
