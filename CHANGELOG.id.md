# Catatan perubahan

**Bahasa / Language / Idioma:** [English](CHANGELOG.md) · [Bahasa Indonesia](CHANGELOG.id.md) · [Español](CHANGELOG.es.md)

Catatan ini merangkum perubahan yang terlihat pengguna. Isinya tidak berarti rilis stabil sudah diterbitkan.

## Belum dirilis

- Menambahkan antarmuka desktop Tkinter opsional melalui `amxtriage gui`. Pemula dapat memilih log lokal, folder source Pawn opsional, bahasa laporan English/Indonesia/Spanyol, lalu menyimpan hasilnya.
- Memperluas CI untuk menguji Python 3.10–3.13 di Ubuntu dan Python 3.12 di Windows serta macOS. Menambahkan sharing file untuk rotasi log di Windows dan keluaran teks LF yang konsisten; tes metrik host Linux kini hanya dijalankan di Linux.
- Menambahkan entrypoint bridge Pawn terpisah untuk SA-MP dan open.mp. CI mengompilasi SA-MP dengan Pawn compiler v3.10.10 dan `samp-stdlib` yang dipatok, serta open.mp dengan compiler v3.10.11 dan `omp-stdlib` yang dipatok.
- Menambahkan versi Bahasa Indonesia dan Spanyol untuk panduan platform/rilis serta kebijakan keamanan, bersama panduan rilis, dukungan platform, dan pengaturan repositori.
- Memperbarui metadata paket untuk menjelaskan CLI dan GUI desktop opsional.

### Batasan yang diketahui

- Bridge Pawn berhasil dibangun di CI, tetapi pengiriman alert di dalam game masih perlu diuji pada server staging SA-MP/open.mp.
- Belum ada adapter API DDoS/provider otomatis atau anti-cheat sisi server. Provider hosting tidak berbagi satu API manajemen universal; adapter khusus provider perlu divalidasi dan diaktifkan secara eksplisit.
- Belum ada aplikasi native Android atau iOS. GUI ditujukan untuk desktop dengan Tkinter.
- Kompatibilitas compiler hanya diverifikasi untuk toolchain CI yang disebutkan, bukan semua versi Pawn lama atau mendatang.
