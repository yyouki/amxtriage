# Guía de publicación, plataformas y proveedores de alojamiento

**Bahasa / Language / Idioma:** [English](RELEASE_AND_PLATFORM_SUPPORT.md) · [Bahasa Indonesia](RELEASE_AND_PLATFORM_SUPPORT.id.md) · [Español](RELEASE_AND_PLATFORM_SUPPORT.es.md)

Dokumen ini membedakan dukungan yang telah diuji dari kemungkinan portabilitas. Dokumen ini bukan sertifikasi untuk semua penyedia hosting atau sistem operasi.

## Deskripsi repositori GitHub yang disarankan

> Analisis log lintas platform untuk SA-MP/open.mp: runtime error Pawn, crash, diagnostik compiler, dan notifikasi admin. Menyediakan CLI, GUI desktop, preview/apply patch aman, dan katalog kompatibilitas plugin.

Topik yang disarankan: `samp`, `openmp`, `pawn`, `log-analysis`, `server-monitoring`, `python`, `developer-tools`.

## Matriks dukungan runtime

| Target | Status dukungan saat ini |
|---|---|
| Windows desktop | CLI diuji dengan Python 3.10–3.13; GUI memerlukan Tkinter. |
| macOS desktop | CLI diuji dengan Python 3.10–3.13; GUI memerlukan Tkinter. |
| Linux desktop/server | CLI diuji dengan Python 3.10–3.13; GUI memerlukan Tkinter dan sesi display. Metrik opt-in hanya tersedia di Linux. |
| Server Linux headless | CLI dan monitor sesuai digunakan; GUI tidak dapat berjalan tanpa display desktop. |
| Android | Tidak ada aplikasi native Android atau target CI. |
| iOS/iPadOS | Tidak ada aplikasi native iOS atau target CI. |
| BSD/Unix lain | Belum disertifikasi oleh matriks CI saat ini. |
| Bridge Pawn SA-MP | Target kompilasi CI: `pawn-lang/compiler v3.10.10` dengan `samp-stdlib` yang dipatok; pengiriman live tetap perlu verifikasi staging. |
| Bridge Pawn open.mp | Target kompilasi CI: `openmultiplayer/compiler v3.10.11` dengan `omp-stdlib` yang dipatok; pengiriman live tetap perlu verifikasi staging. |
| Versi compiler Pawn lain | Tidak dijamin. Kompilasi dan uji staging dengan compiler serta include target yang tepat. |

Istilah “lintas platform” tidak berarti semua OS, arsitektur CPU, rilis Python, ABI plugin, atau versi compiler telah diuji. Hanya kombinasi yang dicantumkan CI yang diverifikasi pada tingkat build/test.

## Provider hosting dan batas mitigasi DDoS

Tidak ada API manajemen tunggal yang digunakan semua perusahaan hosting. API provider, hak akun, paket produk, protokol, model firewall, dan kemampuan mitigasi berbeda-beda.

| Provider/produk | Kemampuan yang didokumentasikan secara resmi | Status amxtriage |
|---|---|---|
| Cloudflare Spectrum | Aplikasi Spectrum dapat dibuat melalui dashboard atau API; dukungan UDP dan field API bergantung paket. [Panduan resmi](https://developers.cloudflare.com/spectrum/get-started/). | Belum ada adapter API otomatis. |
| OVHcloud Game DDoS Protection | OVH mendokumentasikan kemampuan Game Firewall dan protokol game per-IP melalui API. [Panduan resmi](https://docs.ovhcloud.com/en/guides/bare-metal-cloud/dedicated-servers/firewall-game-ddos). | Belum ada adapter API otomatis. |
| AWS Shield Advanced | Memiliki API khusus untuk protection, serangan, dan resource terkait. [Operasi API resmi](https://docs.aws.amazon.com/waf/latest/DDOSAPIReference/API_Operations.html). | Belum ada adapter otomatis; arsitektur endpoint game perlu dikonfirmasi. |
| DigitalOcean Cloud Firewalls | Aturan API mengontrol trafik ke/dari Droplet; ini sendiri bukan jaminan penyaringan DDoS volumetrik khusus game. [API resmi](https://docs.digitalocean.com/products/networking/firewalls/reference/api/). | Belum ada adapter API otomatis. |
| Hetzner Cloud Firewalls | API dapat mengelola aturan firewall masuk/keluar; aturan firewall tidak sama dengan mitigasi DDoS universal. [API resmi](https://docs.hetzner.cloud/reference/cloud). | Belum ada adapter API otomatis. |
| Host lain dan panel reseller | API serta produk proteksi berbeda; beberapa provider tidak menyediakan API publik. | Konfigurasi manual sampai adapter khusus didokumentasikan dan diuji. |

Pawn bridge adalah notifikasi diagnostik lokal, bukan mitigasi DDoS atau anti-cheat. Analisis log tidak dapat menghentikan trafik yang sudah memenuhi kapasitas koneksi upstream.

Adapter provider yang nyata membutuhkan endpoint terdokumentasi, identitas resource yang dilindungi, izin minimum, opt-in eksplisit, dry-run, audit log, dan tes staging. Adapter tidak boleh otomatis memblokir alamat atau mengubah firewall hanya berdasarkan sinyal heuristik dari log.

## Pengaturan repositori GitHub yang disarankan

Deskripsi/topik repositori adalah metadata GitHub, bukan file source. Pengaturan yang disarankan untuk rilis publik:

1. **About:** gunakan deskripsi dan topik di atas; kosongkan Website kecuali situs resmi tersedia.
2. **Default branch/ruleset:** pertahankan `main` sebagai default. Wajibkan status CI berhasil, blokir force-push dan penghapusan branch, serta wajibkan pull request untuk kontributor eksternal.
3. **Actions:** gunakan izin workflow minimum. CI saat ini memerlukan `contents: read`. Sebelum rilis stabil yang diperketat, pin GitHub Actions pihak ketiga ke commit SHA yang sudah ditinjau.
4. **Security:** aktifkan Dependabot alerts/security updates, secret scanning, dan push protection bila tersedia. Siapkan `SECURITY.md` serta pelaporan kerentanan privat bila tersedia.
5. **Kualitas rilis:** pelihara changelog, kebijakan versi/tag, release notes, wheel dan source distribution, checksum artifact bridge, serta petunjuk staging/rollback.
6. **Issues:** minta OS, versi Python, jenis/versi server, versi compiler, dan log minimal yang sudah disensor. Jangan unggah kredensial RCON, kata sandi pemain, atau data privat hosting.

Koneksi GitHub yang tersedia untuk tugas ini bisa mengubah file source dan membaca metadata, tetapi tidak bisa mengedit deskripsi/topik About atau ruleset branch. Terapkan pengaturan tersebut melalui antarmuka GitHub Settings/About.

## Checklist penerimaan rilis

- [ ] CI lulus untuk Python 3.10–3.13 dan kedua kombinasi compiler/include Pawn yang disebutkan.
- [ ] Bridge diuji pada staging dengan build server dan izin yang tepat.
- [ ] GUI diuji pada desktop Windows, macOS, dan Linux; CLI berfungsi pada Linux headless.
- [ ] Dokumentasi English, Indonesia, dan Spanish saling tertaut.
- [ ] Kombinasi host/compiler/platform yang belum diuji tetap berstatus unknown.
- [ ] Tidak ada secret produksi atau log privat di fixture/artifact.
- [ ] Changelog, pelaporan keamanan, release notes, dan petunjuk rollback tersedia.
