# CryptoCrops — Farm Checkpoint (number_image) — live verified

**Sumber:** session live (cookie Mahi) + payload `POST /api/farm-checkpoint/verify` dari DevTools
**Waktu probe:** 2026-10-20 08:09–08:15Z
**Akun:** `SawitDES` · `player_id 4ab70b44-9d6e-402a-bc54-6c4953e78d2c` · mode demo

---

## 1. Cookie yang dipakai (valid, teruji)

```
cc_session_v1=xtoNAwYXNTli-2QIFL16MtPxiyI5TfS6cG83uP9K-y8     exp 2026-11-19
cc_registration_v1=0de0566b-...                                exp 2027-10-20
```

Disimpan di `cookies.txt` (Netscape). `client.py` langsung jalan — bootstrap balik 200 dengan
`xp 16, level 1, coins 10, faucet.available true, claim_count 1`.

> Cookie dari HAR memang tidak pernah ada karena exporter strip. Ini yang pertama valid.

---

## 2. State checkpoint (live)

```json
"farm_checkpoint": {
  "required": false,
  "next_challenge_at": 1792485681589,   // 08:41:21Z
  "required_since": null,
  "last_verified_at": 1792483663069     // 08:07:43Z
}
```

- **`next_challenge_at` = last_verified + 2.018.520 ms ≈ 33 mnt 38 dtk.**
- Timer **tidak** reset saat `/challenge` dipanggil ketika belum due (sudah diuji — nilai tetap).
- `required_since` terisi hanya saat gate benar-benar aktif. Di payload Mahi: `1792482528910`
  (07:48:48Z), yaitu **19 menit** sebelum verifikasi 08:07:43 — gate tidak langsung memblokir,
  tapi menandai kapan kewajiban itu mulai.

Artinya gate muncul tiap ±34 menit, bukan tiap aksi.

---

## 3. Endpoint challenge — ditemukan lewat probe

| Route | Hasil |
|---|---|
| `GET /api/farm-checkpoint` | `NOT_FOUND` |
| `GET /api/farm-checkpoint/challenge` | `NOT_FOUND` |
| **`POST /api/farm-checkpoint/challenge`** | **ada** — `{"attempt_id": "<uuid>"}` |
| `POST /api/farm-checkpoint/challenge` tanpa body | `400 INVALID_REQUEST "attempt_id is invalid."` |
| `POST /api/farm-checkpoint/start` | `FARM_SECURITY_UPDATED` → route ada, tapi menolak sesi/ticket basi |
| `POST /api/farm/checkpoint*` | `NOT_FOUND` |

Jadi sumber gambar **bukan** bootstrap. Alurnya:

```http
POST /api/farm-checkpoint/challenge
{"attempt_id":"b979569a-94b9-4d9c-95a3-14d45226214b"}
```

Saat gate tidak aktif, server balas langsung **verified tanpa gambar**:

```json
{"verified": true,
 "checkpoint": {"required": false, "next_challenge_at": 1792485681589,
                "required_since": null, "last_verified_at": 1792483663069}}
```

Saat gate aktif, response ini yang berisi `number_image` + `captcha_ticket`
(bentuk pastinya ditangkap otomatis oleh `wait_checkpoint.py` → `captures/`).

---

## 4. Kontrak verify (dari payload Mahi, terbukti 200)

```http
POST /api/farm-checkpoint/verify
content-type: application/json
origin: https://cryptocrops.net
referer: https://cryptocrops.net/farm/
```

```json
{"attempt_id":"9684441e-c6a1-44ae-b827-5f0a396ce991",
 "required_since":1792482528910,
 "captcha_number":"059",
 "captcha_ticket":"WyJmYXJtLW51bWJlci12MSIs...<b64>.<64 hex>"}
```

```json
{"verified": true,
 "checkpoint": {"required": false, "next_challenge_at": 1792485681589,
                "required_since": null, "last_verified_at": 1792483663069}}
```

Tidak ada field tambahan, tidak ada signature klien, tidak ada header khusus selain referer.

### 4.1 Anatomi ticket

`captcha_ticket = base64(payload) + "." + <64 hex>`

```json
["farm-number-v1",
 "4ab70b44-9d6e-402a-bc54-6c4953e78d2c",   // player_id
 "1792482528910",                           // required_since (string!)
 "9684441e-c6a1-44ae-b827-5f0a396ce991",    // attempt_id — sama dengan body
 "cryptocrops.net",
 1792483655248,                             // issued_at (08:07:35Z)
 "ad4f0c8b-69e0-4371-b6b0-7d2a0426ee48"]    // nonce
```

Sama polanya dengan ticket Turnstile faucet: payload terbaca, segmen setelah titik = `cdata`
(HMAC/secret server, bukan `sha256(payload)` — sudah diuji tidak match).

**Konsekuensi:** ticket terikat ke `player_id` + `attempt_id` + `required_since`. `attempt_id`
dipilih klien, jadi urutannya: generate uuid → minta challenge → ticket diterbitkan untuk uuid itu →
verify dengan uuid yang sama. Tidak bisa dipakai ulang untuk attempt lain.

`issued_at` 08:07:35 → verify 08:07:43 = **8 detik**, cukup untuk OCR manusia/bot. Tidak ada TTL
panjang yang terlihat; tantangan dianggap hidup sampai `required_since` berganti.

### 4.2 Captcha-nya cuma 3 digit

`"captcha_number": "059"` — **3 digit, leading zero dipertahankan**. Ruang jawaban hanya 1.000.

Implikasi:
- OCR nyaris bebas error (ddddocr pada digit bersih ≈ 100%).
- Brute force **mungkin secara matematis** (1.000 percobaan), tapi belum diketahui apakah verify
  membatasi attempt per `attempt_id`/`required_since`. Setiap tebakan salah kemungkinan membakar
  ticket dan memaksa challenge baru (ticket terikat `attempt_id`), sehingga brute force = 1.000
  challenge. Tidak ekonomis dibanding OCR.

---

## 5. Bentuk asli challenge — tertangkap live (15:41:27)

```json
{
  "captcha": {
    "provider": "number_image",
    "configured": true,
    "mandatory": true,
    "ticket": "WyJmYXJtLW51bWJlci12MSIs...<309 char>",
    "image": "data:image/png;base64,iVBORw0KGgo...<28.102 char>",
    "expires_at": 1792485989291
  },
  "checkpoint": {
    "required": true,
    "next_challenge_at": 1792485681589,
    "required_since": 1792485681589,
    "last_verified_at": 1792483663069
  },
  "attempt_id": "e3e37c96-db42-4c63-87e6-23d42c7706b4"
}
```

- gambar di `captcha.image`, data-URI PNG, 232×90 px, 21.059 byte setelah decode.
- `captcha.expires_at` = `required_since` + 307.702 ms (**±5 menit**), bukan TTL 15 menit.
- `required_since` saat gate aktif = **`next_challenge_at` yang lama**. Jadi timer yang sama
  dipakai dua kali: sebagai jadwal, lalu sebagai cap waktu mulai wajib.
- `attempt_id` di-echo server; harus sama dengan yang dikirim.

Isi gambar: tiga digit, warna hijau tua, di atas tekstur kertas, dengan garis coretan
horizontal dan bintik noise. ddddocr membaca **971** benar pada percobaan pertama.

Hasil verify live:

```json
{"verified": true,
 "checkpoint": {"required": false,
                "next_challenge_at": 1792488083428,
                "required_since": null,
                "last_verified_at": 1792485691354}}
```

Interval gate berikutnya: `1792488083428 − 1792485691354` = **2.392.074 ms ≈ 39 mnt 52 dtk**.
Dua sampel sejauh ini: 33 mnt 38 dtk dan 39 mnt 52 dtk → jadwalnya diacak dalam rentang ±35–40 menit.

---

## 6. Tool yang dibuat

### `checkpoint.py`

```bash
python checkpoint.py --status              # required + sisa detik ke gate berikutnya
python checkpoint.py --once                # challenge -> OCR -> verify (kalau due)
python checkpoint.py --once --number 059   # skip OCR
python checkpoint.py --watch               # pantau, solve otomatis tiap gate muncul
```

Isi:
- `find_image()` — menelusuri JSON response secara rekursif, decode data-URI/base64, validasi
  magic PNG/JPEG/SVG. Tidak bergantung pada nama field (belum diketahui saat ditulis).
- `find_key()` — ambil `captcha_ticket` / `required_since` / hint panjang digit dari kedalaman mana pun.
- `decode_ticket()` — bongkar payload ticket untuk debugging.
- `Ocr` — ddddocr (terpasang, `onnxruntime 1.31`, Python 3.14), fallback pytesseract.
- Semua response mentah disimpan ke `captures/` dengan `--dump`.

### `client.py` — method baru

```python
api.checkpoint_challenge(attempt_id=None)   # POST /api/farm-checkpoint/challenge
api.checkpoint_verify(attempt_id, required_since, captcha_number, captcha_ticket)
```

`checkpoint_due()` yang lama tetap dipakai `tick()` sebagai guard: kalau gate aktif, automation
berhenti sebelum menembak harvest yang pasti ditolak.

### `wait_checkpoint.py` — penangkap bentuk challenge

Tidur sampai `next_challenge_at + 5 s`, lalu poll + solve + dump. Dijalankan sekali untuk
mendapatkan schema asli response saat gate aktif (field gambar, nama ticket, hint panjang digit).

---

## 7. Urutan operasi yang benar

```
bootstrap
  ├─ farm_checkpoint.required == false dan now < next_challenge_at  → lanjut farming
  └─ gate aktif / timer lewat
        ├─ attempt_id = uuid4()
        ├─ POST /api/farm-checkpoint/challenge {attempt_id}
        │     └─ verified:true  → tidak perlu apa-apa
        ├─ OCR number_image  → "059"
        └─ POST /api/farm-checkpoint/verify {attempt_id, required_since,
                                             captcha_number, captcha_ticket}
              └─ verified:true → next_challenge_at +34 mnt, lanjut farming
```

`required_since` harus diambil dari response challenge (atau dari payload ticket indeks ke-2),
**bukan** dari `time.time()`.

---

## 8. Yang belum terbukti

- Apakah gate memblokir **semua** write (plant/harvest/sell) atau hanya harvest.
- Ada/tidaknya limit attempt per gate.
- Apakah `FARM_SECURITY_UPDATED` muncul kalau ticket dipakai setelah `next_challenge_at` bergeser
  (indikasi validasi waktu ketat).
- Apakah checkpoint ikut aktif saat faucet claim (di HAR faucet tidak ada checkpoint).
