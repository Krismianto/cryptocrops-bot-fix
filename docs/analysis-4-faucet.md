# CryptoCrops — Faucet & Turnstile (HAR #3)

**Sumber:** `C:\Users\Admin\Downloads\CryptoCrops\cryptocrops.net.-faucetClaim.har`
**Ukuran:** 1.283.257 byte · 16 entry · 1 page · tanpa cookie (exporter strip)
**Jendela:** 2026-10-20 07:40:48Z → ±07:41:43Z
**Solver:** [Theyka/Turnstile-Solver](https://github.com/Theyka/Turnstile-Solver) (patchright + Quart API)

---

## 1. Alur lengkap (4 langkah, 14,8 detik)

| # | Request | Body | Response |
|---|---|---|---|
| 004 | `POST /api/earn/faucet-challenge` | `{}` | 764 B, challenge + ticket |
| 005–009 | (traffic Turnstile di `/cdn-cgi/challenge-platform/...`) | – | token dihasilkan browser |
| 012 | `POST /api/earn/faucet` | 1.301 B | 258 B, klaim sukses |
| 013–015 | `GET /api/bootstrap` | – | state baru |

Jarak 004 → 012 = **14.841 ms** (itu waktu solve Turnstile, bukan server).

### 1.1 Challenge

```http
POST /api/earn/faucet-challenge
content-type: application/json
{}
```

```json
{"challenge":{"challenge_id":"afc7f6ea-f731-4e64-a5be-05f9920f8f41",
              "expires_at":1792482349785},
 "captcha":{"provider":"turnstile","configured":true,"mandatory":true,
            "site_key":"0x4AAAAAAE8SO-yZVCky9wK7"},
 "verification":{"provider":"turnstile","configured":true,"mandatory":true,
                 "site_key":"0x4AAAAAAE8SO-yZVCky9wK7",
                 "action":"faucet_claim",
                 "cdata":"78e0e6dedabe7344df9b4585690dc3e77c13726ed317b7a2782203b84111959c",
                 "ticket":"WyJ0dXJuc3RpbGUtdjEiLC...",
                 "expires_at":1792482349785}}
```

- **TTL challenge = 300 detik** (5 menit). Lewat itu, harus minta challenge baru.
- `cdata` = 64 hex char (terlihat seperti SHA-256, tapi **bukan** `sha256(ticket)` atau `sha256(payload)` — sudah diuji, tidak match; jadi kemungkinan HMAC/random yang disimpan server, bukan hash yang bisa dihitung ulang).
- `ticket` = `base64(payload) + "." + cdata`. Payload setelah di-decode:

```json
["turnstile-v1","faucet_claim","4ab70b44-9d6e-402a-bc54-6c4953e78d2c",
 "afc7f6ea-f731-4e64-a5be-05f9920f8f41","","cryptocrops.net",
 1792482049785,"c7831f35-b422-46a0-aa47-67a7296c5980"]
```

Bindings: versi, action, `player_id`, `challenge_id`, string kosong, host, issue time, nonce UUID. Ticket **wajib di-echo persis**; tidak bisa dipalsukan tanpa tahu cara server memvalidasi (dan challenge_id tetap dicek di DB).

### 1.2 Claim

```http
POST /api/earn/faucet
content-type: application/json
origin: https://cryptocrops.net
referer: https://cryptocrops.net/faucet/
```

```json
{"idempotency_key":"35f87a0c-52fa-40ef-990e-98bafc0cd97f",
 "faucet_challenge":"afc7f6ea-f731-4e64-a5be-05f9920f8f41",
 "captcha_token":"1.8vGTfAqoiCs0c3DuR54XM8NyVPXwE72wO2y-QjH5WBxG3...",
 "captcha_ticket":"WyJ0dXJuc3RpbGUtdjEiLC..."}
```

Token format `1.<base64url>.<base64url>.<hex>` — token Turnstile v0 standar. Tidak ada field tambahan, tidak ada signature klien.

Response:

```json
{"claimed":{"claim_id":"85f81fb7-03ba-4376-a425-f1791b00b038",
 "base_coins":10,"league_bonus_bps":0,"bonus_coins":0,"total_coins":10,
 "farm_coin_balance":10,"farm_xp_earned":1,
 "sponsored_coins_toward_next_farm_xp":0,"farm_xp":16,
 "next_claim_at":1792482965480}}
```

### 1.3 Dampak ke state (dari bootstrap 001 vs 013)

| field | sebelum | sesudah |
|---|---|---|
| `farm.faucet.available` | true | false |
| `farm.faucet.claim_count` | 0 | 1 |
| `farm.faucet.next_claim_at` | 0 | 1792482965480 |
| `farm.profile.farm_coins` | 0 | 10 |
| `farm.farm_progression.xp` | 15 | 16 |
| `missions.daily-faucet-coins-200` | 0/200 | 10/200 |
| `missions.weekly-faucet-coins-1000` | 0/1000 | 10/1000 |

**Cooldown = 902.501 ms ≈ 15 menit 2,5 detik** (`next_claim_at` − waktu claim).

Kolom `sponsored_coins_toward_next_farm_xp: 0` mengonfirmasi `xp_sources.sponsoredCoinsPerXp: 10` → **10 coin = 1 farm xp**.

---

## 2. Yield faucet

- 10 coin + 1 xp per klaim, cooldown 15 mnt 2,5 dtk.
- **≈ 95,6 klaim/hari → 956 coin + 95,6 xp/hari.**
- Plot ke-5 (1.000 coin) = **1,05 hari faucet murni**.
- Level 2 (250 xp) kalau hanya faucet = 2,6 hari; lewat panen radish jauh lebih cepat.

Faucet bukan sumber poin — ini sumber **coin**, satu-satunya yang murah. Untuk capacity upgrade, faucet adalah mesin utamanya.

---

## 3. Integrasi Turnstile-Solver

Solver menjalankan browser (patchright) yang **mencegat navigasi** ke `url` dan menyajikan HTML sintetis berisi widget, lalu membaca `[name=cf-turnstile-response]`. Karena route di-fulfill pada URL asli, **origin dokumen tetap `cryptocrops.net`** — itu yang membuat token lolos validasi hostname.

API-nya:

```http
GET /turnstile?url=https://cryptocrops.net/faucet/&sitekey=0x4AAAAAAE8SO-yZVCky9wK7&action=faucet_claim&cdata=<hex>
→ {"task_id":"..."}   (HTTP 202)

GET /result?id=<task_id>
→ {"elapsed_time":7.6,"value":"0.KBtT-r..."}   atau "CAPTCHA_NOT_READY"
```

Dua parameter yang **wajib** ikut dikirim, kalau tidak token akan ditolak server:

1. **`action=faucet_claim`** — server memberi tahu action-nya di response challenge; Turnstile menyimpannya di token dan server membandingkannya.
2. **`cdata=<hex dari challenge>`** — tanpa ini, `cdata` di token kosong dan validasi server gagal.

`sitekey` = `0x4AAAAAAE8SO-yZVCky9wK7` (sama dengan yang di `security.turnstile_site_key`).

Jalankan solver:

```bash
git clone https://github.com/Theyka/Turnstile-Solver
cd Turnstile-Solver
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
python -m patchright install chromium
python api_solver.py --headless true --useragent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36" --browser_type chromium --debug true
```

`--headless` di solver ini parsing-nya `type=bool`, jadi **harus** `--headless true` (atau `false`), bukan flag kosong. Tanpa `--useragent`, headless ditolak.

Kalau Turnstile menolak headless, pakai `--browser_type camoufox` (tanpa useragent) atau jalankan non-headless di sesi RDP.

---

## 4. Klien yang dibuat

`faucet.py` — alur penuh, dengan polling solver dan penanganan retry:

```bash
python faucet.py --once                  # satu klaim
python faucet.py --loop                  # ikut cooldown otomatis
python faucet.py --once --dry-run        # solve token saja, tidak submit
python faucet.py --loop --solver http://127.0.0.1:5000
```

Logika di dalamnya:

1. `bootstrap()` → cek `farm.faucet.available`; kalau cooldown, langsung tidur sampai `next_claim_at`.
2. `POST /api/earn/faucet-challenge`.
3. Kirim ke solver dengan `action` + `cdata` dari response.
4. Poll `/result` sampai token keluar atau timeout 90 s.
5. `POST /api/earn/faucet` dengan token + ticket.
6. Kalau ditolak (bukan 401/403), ulangi dengan **challenge baru** — token lama tidak bisa dipakai dua kali.

Method `faucet_challenge()` dan `faucet_claim()` juga sudah masuk ke `client.py`.

---

## 5. Titik gagal yang perlu diperhatikan

| Gejala | Penyebab | Penanganan |
|---|---|---|
| `AUTHENTICATION_REQUIRED` (401) | cookie sesi hilang/kedaluwarsa | ambil ulang dari DevTools |
| challenge tapi claim 4xx | `cdata` tidak dikirim ke widget | pastikan param `cdata` ikut |
| token valid tapi ditolak | `action` salah / tidak dikirim | pakai `faucet_claim` |
| `CAPTCHA_FAIL` dari solver | headless terdeteksi | camoufox / non-headless |
| challenge kedaluwarsa | solve > 300 s | turunkan timeout solver, retry |
| `next_claim_at` tetap | klaim sudah tercatat (idempotent) | cek `claim_count` di bootstrap |

Solver tidak membawa cookie sesi — itu **tidak masalah**, karena Turnstile hanya memvalidasi origin + sitekey + action + cdata. Cookie hanya dibutuhkan oleh request API CryptoCrops.

---

## 6. Rate limit — gate kedua yang tidak terlihat di HAR

Setelah solver live dan token berhasil dibuat, `POST /api/earn/faucet` menolak:

```json
{"error":"FAUCET_RATE_LIMITED",
 "message":"Too many faucet attempts. Try again in 837 seconds."}
```

Sifatnya (terukur):

- **fixed window**, bukan sliding. Percobaan berikutnya berbunyi `816 s`, `814 s` — mengikuti jam,
  bukan menambah hukuman.
- **`faucet.available: true` dan `next_claim_at` yang sudah lewat TIDAK berarti boleh klaim.**
  Dua gate terpisah: cooldown 15 menit (state) dan rate limit percobaan (anti-bot).
- **challenge yang diminta tapi tidak disubmit ikut dihitung.** `--dry-run` membakar kuota.
- begitu kena, `/api/earn/faucet-challenge` juga ikut diblokir dengan pesan yang sama — jadi
  retry hanya memperpanjang.

Konsekuensi untuk otomasi: satu challenge = satu percobaan. Jangan pernah minta challenge
kalau token belum pasti dipakai. `faucet.py` sekarang mendeteksi `FAUCET_RATE_LIMITED`, membaca
sisa detik dari pesan, lalu tidur — bukan retry.

Durasi 837 s di atas setara ±14 menit, sepadan dengan cooldown 902 s. Jadi irama normal
(1 klaim / 15 menit) tidak akan pernah menyentuh limit; yang menyentuhnya adalah challenge
yang dipanggil berulang tanpa submit.

---

## 7. Hasil uji live — dan kenapa token generik ditolak

Solver generik (Theyka) berjalan dan menghasilkan token:

```
[1] challenge 4280c6d3… ttl=301s action=faucet_claim cdata=550ea596da…
[1] token 1.73J5fme-ht3-… (858 chars)
```

Tapi submit selalu:

```json
{"error":"FAUCET_CAPTCHA_FAILED","message":"Complete the security check before claiming the faucet."}
```

### 7.1 Akar masalah: implicit vs explicit render

`/turnstile-check.js?v=0.58.1` milik situs:

```js
const id = api.render(element, {
  sitekey: config.site_key,
  action:  config.action,     // "faucet_claim"
  cData:   config.cdata,      // 64 hex dari /api/earn/faucet-challenge
  ...
});
```

- Situs memakai **explicit render** dan mengirim `cData` sebagai opsi API.
- Theyka solver memakai **implicit render** (`<div class="cf-turnstile" data-cdata="…">`).
- Token yang lahir dari implicit render tidak membawa cdata yang server harapkan.
  Server membandingkan `cdata` token dengan `cdata` ticket → beda → `FAUCET_CAPTCHA_FAILED`.

Token tetap "valid" secara umum (858 char, format `1.<b64>.<b64>.<hex>`), tapi tidak terikat
ke challenge yang disubmit. Karena itu `action` dan `cdata` **tidak cukup** dikirim sebagai
atribut HTML — harus lewat API render.

### 7.2 Konsekuensi arsitektur

Memisahkan "ambil ticket di Python" dan "solve di browser" juga boros: setiap
`/faucet-challenge` memakan kuota rate limit, dan cdata/ticket harus berasal dari panggilan
yang sama dengan widget.

Solusi yang dipakai sekarang — `faucet_ui.py`:

1. buka `https://cryptocrops.net/faucet/` di Patchright dengan cookie sesi;
2. situs sendiri yang memanggil `/faucet-challenge` dan memasang widget (action + cData dijamin cocok);
3. tunggu tombol `[data-claim-faucet]` aktif (artinya token sudah masuk `state.faucetTurnstileToken`);
4. klik → tangkap response `/api/earn/faucet`.

Satu sesi, satu challenge, satu klaim.

Catatan teknis: `chromium.launch(channel="chromium")` dipakai untuk headless — headless shell
bawaan Playwright tidak punya WebGL dan Turnstile langsung `error-callback`
("The security check failed. Retry the check above.").

---

## 8. Yang belum diketahui

- apakah server memanggil Cloudflare `siteverify` dengan `remoteip` (kalau ya, IP solver dan IP klien harus sama — saat ini satu mesin, jadi aman).
- apakah ada limit klaim per IP per hari di luar cooldown 15 menit (tidak ada header rate-limit di HAR).
- apakah `farm_checkpoint` (number_image) bisa muncul di jalur faucet — di HAR ini tidak; checkpoint hanya terlihat di `/farm/`.
- masa hidup cookie sesi: 30 hari menurut capture #1, tapi `cf_clearance` biasanya lebih pendek dan bisa memaksa re-solve.
