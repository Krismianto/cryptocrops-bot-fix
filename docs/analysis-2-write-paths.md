# CryptoCrops — Bedah HAR #2: write-path (plant / harvest / sell)

**Sumber:** `C:\Users\Admin\Downloads\CryptoCrops\cryptocrops.net.har-harvest-selling-planting.har`
**Ukuran:** 1.143.988 byte · HAR 1.2 · `WebInspector/537.36` · 14 entry · 0 page · tanpa cookie
**Jendela:** 2026-10-20 07:32:23.556Z → 07:32:49.946Z (26,4 detik)
**REA:** `inspect_web_network_capture` → `ev_f6465281a1654c94399c757f5d1a99e43026ce44de2dd682bfc3f11123287916`
**Decoder:** `har-schema/lossless-json` · har-schema@2.0.0 · jsonc-parser@3.3.1 · lossless-json@4.3.1
**Confidence:** observed (semua angka di bawah dibaca dari body response, bukan inferensi)

---

## 1. Peta entry (14 record, urut)

| # | Method | Path | Status | Ukuran | Catatan |
|---|--------|------|--------|--------|---------|
| 000 | GET | `/api/bootstrap` | 200 | 128.885 B | state awal |
| 001 | POST | `/api/farm/harvest` | 200 | 355 B | panen radish (plot 3) |
| 002 | GET | `/api/bootstrap` | 200 | 128.885 B | **identik** dengan 000 |
| 003 | POST | `/api/farm/harvest` | 200 | 356 B | panen radish (plot 3) kedua |
| 004 | GET | `/api/bootstrap` | 200 | 128.496 B | inventory 2, crops 2 |
| 005 | POST | `/api/farm/plant` | **201** | 189 B | wheat → plot 3 |
| 006 | GET | `/api/bootstrap` | 200 | 128.888 B | crops 3 |
| 007 | POST | `/api/farm/plant` | **201** | 189 B | wheat → plot 4 |
| 008 | GET | `/api/bootstrap` | 200 | 129.280 B | crops 4 = kapasitas penuh |
| 009 | GET | `/api/farm/sell-preview?seed_id=radish&quantity=1` | 200 | 121 B | 11 pts |
| 010 | GET | `/api/farm/sell-preview?seed_id=radish&quantity=2` | 200 | 121 B | 22 pts |
| 011 | POST | `/googletag/ga/g/c?...tid=G-2H4HRF6D77` | 204 | 0 B | GA4 proxy |
| 012 | POST | `/api/farm/sell` | 200 | 306 B | 22 pts masuk pool |
| 013 | GET | `/api/bootstrap` | 200 | 129.123 B | inventory kosong, pool 22 |

Pola klien: **setiap write selalu diikuti GET bootstrap**. Jadi server tidak mengembalikan state penuh pada write; klien re-fetch. Artinya delta state harus dibaca dari bootstrap, bukan dari response write.

---

## 2. Kontrak write-path (final, terbukti)

### 2.1 `POST /api/farm/plant` → 201

Request:
```json
{"idempotency_key":"c21deeee-9ab6-4b83-aa6a-cfb937402225","seed_id":"wheat","plot_index":3}
```
Headers: `content-type: application/json`, `origin: https://cryptocrops.net`, `referer: /farm/`.
**Tidak ada** CSRF token, nonce, captcha, signature, version field, atau farm-checkpoint token.

Response:
```json
{"planted":{"crop_id":"89f6f72c-3ca2-4f5f-91b3-983cb08aad1c","plot_index":3,
"seed_id":"wheat","ready_at":1792485156663,"perfect_until":1792486056663,
"pre_fresh_points":120,"yield_level":1}}
```

`crop_id` = UUID v4 yang **diterbitkan server**, dipakai sebagai handle untuk harvest. `ready_at`/`perfect_until`/`pre_fresh_points` semuanya ditentukan server.

### 2.2 `POST /api/farm/harvest` → 200

Request:
```json
{"idempotency_key":"0283f77f-5b50-494b-b5bb-37a17f9de6f0","crop_id":"d88e7da8-dbba-4972-a5fd-be97965bc579"}
```

Response:
```json
{"harvested":{"batch_id":"63b58507-d73a-4688-96bc-e6cbe7f80a86","seed_id":"radish",
"quantity":1,"plot_level":1,"point_value":11,"freshness_bps":9500,
"perfect_harvest":false,"packing_bonus_bps":0,"perfectly_packed":false,
"fresh_until":1793086345260,"mastery_level":0,"mastery_harvests":1,
"mastery_progress":1,"farm_xp_earned":5,"farm_xp":5,"farm_level":1}}
```

Panen menghasilkan **batch** (bukan coin). Batch masuk inventory sebagai fresh produce dengan masa segar 7 hari.

Harvest kedua (6 detik kemudian) → `mastery_harvests: 2`, `farm_xp: 10`, `batch_id` baru. **Tidak ada cooldown, tidak ada rate-limit header, tidak ada captcha.**

### 2.3 `GET /api/farm/sell-preview?seed_id=&quantity=`

```json
{"preview":{"seed_id":"radish","quantity":1,"points":11,
"harvest_pass_xp_reward":0,"earliest_fresh_until":1793086345260}}
```
`quantity=2` → `points: 22`. **Linear, tanpa diskon bulk, tanpa fee.** `earliest_fresh_until` = bukti FIFO by freshness (yang paling cepat basi dijual dulu).

### 2.4 `POST /api/farm/sell` → 200

Request:
```json
{"idempotency_key":"352acc26-f882-4392-9e4c-d19cc2885056","seed_id":"radish","quantity":2}
```
**Tidak ada `batch_id`.** Server memilih batch sendiri (FIFO). Artinya harga tidak bisa dikunci klien.

Response:
```json
{"sold":{"sale_id":"1d5e8dba-f8f8-4785-bf32-4d31d629f830","sold_at":1792481570421,
"seed_id":"radish","quantity":2,"points":22,"pool_cycle_id":82985,
"pool_total_points":22,"season_total_points":22,"division":"Seedling",
"coin_bonus_bps":0,"pass_xp_earned":0,"harvest_pass_xp":0,
"eligible_for_rewards":false}}
```

`pool_total_points` dan `season_total_points` = **milik player** (bukan global) — keduanya 22 sesuai penjualan.

---

## 3. Ekonomi yang terukur

### 3.1 Rumus poin

```
point_value = floor(pre_fresh_points × freshness_bps / 10000)
```
Bukti: radish `pre_fresh_points` 12, `freshness_bps` 9500 → **11** (12 × 0,95 = 11,4 → 11). Cocok persis.

`freshness_bps` maksimum 10000. Panen di dalam `perfect_until` diasumsikan 10000 (`perfect_harvest: true`) — **belum terbukti**, karena dua panen di capture ini terjadi 18,7 s dan 24,5 s setelah `perfect_until` dan keduanya 9500. Dua hipotesis yang masih hidup:
- (a) di luar window = flat 9500 (−5%),
- (b) decay bertahap 500 bps per ~15–30 s.

Butuh satu panen tepat waktu untuk memutuskan. Dampaknya kecil (5%), tapi untuk optimasi tetap relevan.

### 3.2 Kurva tanaman (dari `crops` di bootstrap)

| seed | cadence | grow | perfect window | `pre_fresh_points` @L1 | pts/jam/plot |
|------|---------|------|----------------|------------------------|--------------|
| radish | Rapid | 300 s (5 mnt) | 120 s | 12 | **144** |
| lettuce | Rapid | 600 s (10 mnt) | 150 s | 24 | **144** |
| carrot | Active | 1.800 s (30 mnt) | 450 s | 66 | 132 |
| wheat | Balanced | 3.600 s (60 mnt) | 900 s | 120 | 120 |

Dengan kapasitas 4 plot: **±576 pts/jam** (radish/lettuce). `yield_level` 1, `plot_upgrades.next_cost` 5.000 coin/level, `max_level` 25.

### 3.3 Pool

```
cycleId        82985
startsAt       2026-10-20 06:00:00Z
endsAt         2026-10-20 12:00:00Z     (6 jam)
harvestCredits 600.000  HC
creditsPerUsd  10.000   → pool = $60 per 6 jam = $240/hari
weather        celestial / "Celestial Night" / bonusBps 2500
estimatedHarvestCredits 9        (untuk 22 pts)
estimatedUsdMicros      900      = $0,0009
```

Implikasi: 22 pts → 9 HC ⇒ total poin semua player di siklus itu ≈ **1,46 juta**. Nilai per poin ≈ 0,41 HC. Pool $60/6 jam dibagi seluruh pemain — ini faucet mikro, bukan income. Dengan 576 pts/jam × 6 jam = 3.456 pts → ±1.400 HC ≈ $0,14 per siklus.

### 3.4 Divisi musim (`league-2026-10-04`, "October 2026 Farmer League")

| Divisi | Threshold | Bonus coin |
|--------|-----------|------------|
| Seedling | 0 | 0 bps |
| Farmhand | 100.000 | 200 bps |
| Cultivator | 500.000 | 500 bps |
| Harvester | 1.500.000 | 800 bps |
| Homesteader | 4.000.000 | 1.200 bps |
| Cropmaster | 10.000.000 | 1.800 bps |

`coin_bonus_bps` di response sell = 0 → konsisten dengan Seedling. Threshold pertama 100.000 pts ≈ 174 jam farming nonstop di 4 plot. Kurva divisi praktis tidak tercapai secara organik dalam satu musim.

### 3.5 `eligible_for_rewards: false`

Muncul saat 22 pts. Belum ada field di bootstrap yang menjelaskan syaratnya (tidak ada `min_points`, tidak ada flag serupa di `pool_progress`). Kandidat: ambang poin minimum per penjualan, atau syarat `freshness_bps`/`perfect_harvest`. **Belum terbukti.**

---

## 4. Temuan paling penting: seed TIDAK berkurang saat plant

Perbandingan `farm.seeds` lintas snapshot:

| snapshot | carrot | lettuce | radish | wheat |
|---|---|---|---|---|
| 004 (sebelum plant) | 1 | 1 | 2 | **2** |
| 006 (setelah plant wheat #1) | 1 | 1 | 2 | **2** |
| 008 (setelah plant wheat #2) | 1 | 1 | 2 | **2** |

Dua `plant` sukses (201), stok wheat tetap 2. Tidak ada penurunan, tidak ada field `planted_count` yang menggantikan.

Kemungkinan:
1. `seeds[].quantity` bersifat dekoratif / hanya untuk display katalog dan plant tidak mengonsumsi stok (bug ekonomi);
2. konsumsi di-settle di tempat lain yang tidak terekspos ke bootstrap (mis. ledger terpisah, atau biaya dipotong saat harvest);
3. plant dibatasi oleh `seed level` + kapasitas plot, bukan stok.

Yang bisa dipastikan: **tidak ada penalti yang terlihat untuk planting berulang**, dan satu-satunya pembatas loop adalah waktu tumbuh + slot plot. Ini menghapus seluruh gate "beli seed" dari ekonomi.

---

## 5. Permukaan penyalahgunaan (diurutkan by dampak)

### H1 — `plot_index` di luar `total_capacity` (probabilitas sedang, dampak tinggi)
`plot_upgrades` punya **28 entri** (plot 1–28), sementara `capacity_upgrade.max_base_capacity` = 24 dan `total_capacity` = 4. Validasi plant hanya terlihat membandingkan `plot_index` dengan kapasitas/occupancy. Kalau server menerima `plot_index` 5–28 tanpa cek kapasitas, satu akun bisa menanam 28 tanaman sekaligus → **7× throughput**, dan itu langsung 7× poin pool.
Bukti pendukung: pada capture ini `plant` ke plot 4 diterima saat `total_capacity` = 4 (index 1-based, jadi masih legal) — jadi batas atas belum teruji sama sekali. **Belum diverifikasi.**

### H2 — seed tidak dikonsumsi (§4)
Loop gratis: plant → tunggu → harvest → sell, tanpa biaya modal. Dampak: ekonomi hanya dibatasi waktu, bukan uang.

### H3 — `quantity` di `/api/farm/sell` (probabilitas rendah–sedang)
`sell` tidak mengirim `batch_id`; server memilih batch. Kalau server tidak meng-clamp `quantity` ke isi inventory, `quantity: 9999` bisa menjual batch yang tidak ada. `sell-preview` juga menerima `quantity` arbitrer — preview untuk 2 item hanya mengembalikan 22 pts tanpa error, tapi itu masih dalam batas stok. Perlu uji `quantity` > stok.

### H4 — tidak ada anti-bot di write-path farm (§2.1, §2.2)
Turnstile hanya di faucet. `farm_checkpoint` (`number_image`, binding ke `player_id`) ada dan `required: false` saat capture, `next_challenge_at` ~16 menit ke depan. Selama jendela `required: false`, harvest/plant/sell bisa dijalankan headless tanpa interaksi manusia. Kalau checkpoint muncul, loop harus berhenti.

### H5 — `idempotency_key` client-generated
UUID v4 dari klien, tanpa server nonce, tanpa TTL yang terlihat. Replay key sama dengan body berbeda tidak teruji. Kalau server menyimpan key sebagai cache response murni (tanpa mengikat body), satu key bisa dipakai untuk banyak harvest berbeda.

### H6 — `/api/bootstrap` 128 KB per write
Setiap aksi diikuti bootstrap penuh (5× dalam 26 detik ≈ 640 KB). Ini amplifier biaya: rate-limit, bandwidth, dan CPU DB. Loop cepat = beban besar dan pola trafik yang sangat mudah dideteksi/dibatasi. Kalau ada WAF rule, ini yang kena duluan.

### H7 — `can_preview_farm: true` untuk akun `demo`
Akun ini `mode: demo` tapi tetap punya `farm_coins`, pool, dan withdrawal path di capture pertama. Perlu dicek apakah flag demo mencegah penarikan atau hanya label UI.

---

## 6. Anti-bot & keamanan transport (observed)

- **Cloudflare** di depan (`cf-ray: …-SIN`, `server: cloudflare`), HTTP/3 via `alt-svc`, body `zstd`.
- Tidak ada header `rate-limit-*` / `retry-after` di response mana pun.
- `cache-control: no-store` di semua endpoint API (kecuali aset statis di capture #1).
- CSP: `frame-ancestors 'self'; object-src 'none'; base-uri 'self'` — tidak ada `script-src`, jadi CSP praktis longgar.
- `strict-transport-security: max-age=31536000; includeSubDomains`.
- `permissions-policy: browsing-topics=(), usb=(), serial=()`.
- **Tidak ada cookie di HAR** (exporter strip). Replay dari file tetap mustahil; butuh sesi hidup.

---

## 7. Yang masih kosong

Belum ada bukti untuk: `/api/farm/upgrade-plot`, `/api/farm/upgrade-capacity`, `/api/farm/fertilize`, `/api/farm/checkpoint` (submit), `/api/farm/orders/{id}/fulfill`, `/api/missions/{id}/claim`, `/api/harvest-pass/claim`, `/api/faucet/claim`, `/api/shop/*`, `/api/withdrawals` (POST), `/api/guilds/*` (write), `/api/crafting/*`.

Checklist capture berikutnya (jalankan di browser, urutan ini):
1. upgrade satu plot (biar `next_cost` dan efek `yield_level` ketahuan),
2. upgrade kapasitas (`capacity_upgrade.available`),
3. pakai fertilizer (minimal 1 rarity),
4. klaim faucet + Turnstile,
5. selesaikan 1 farm order,
6. klaim 1 misi harian yang sudah complete,
7. klaim 1 tier harvest pass,
8. submit farm-checkpoint saat `required: true`,
9. satu percobaan `quantity` > stok di sell (kalau berani, akun alt),
10. satu percobaan `plot_index` 5 saat kapasitas 4 (akun alt, ini yang paling berharga).

---

## 8. Verifikasi silang dengan capture #1

| Field | Capture #1 | Capture #2 | Konsisten? |
|---|---|---|---|
| `player_id` | `4ab70b44-9d6e-402a-bc54-6c4953e78d2c` | sama | ya |
| `farm_checkpoint_binding` | sama dengan `player_id` | sama | ya |
| `turnstile_site_key` | `0x4AAAAAAE8SO-yZVCky9wK7` | sama | ya |
| `creditsPerUsd` | 10.000 | 10.000 | ya |
| `harvestCredits` | 600.000 | 600.000 | ya |
| `cycleId` | 82985 | 82985 | ya |
| `total_capacity` | 4 | 4 | ya |
| `plot_upgrades` | 28 entri | 28 entri | ya |
| `mode` | `demo` | `demo` | ya |
| `can_preview_farm` | true | true | ya |

Tidak ada perubahan skema antara dua capture — kontrak API stabil dalam 9 menit.

---

## 9. Kesimpulan operasional

1. Seluruh write-path farm adalah **JSON POST tanpa token, tanpa captcha, tanpa nonce**. Satu-satunya pertahanan adalah sesi cookie + Cloudflare + farm-checkpoint periodik.
2. `plant` **tidak memotong stok seed** — loop tanam gratis, dibatasi waktu tumbuh dan slot.
3. `harvest` mengembalikan `point_value` final; `sell` hanya memindahkan batch ke pool. Harga tidak bisa dimanipulasi klien.
4. Nilai ekonomi kecil: pool $60/6 jam untuk seluruh pemain. Yang layak dikejar bukan uangnya, tapi **throughput poin** (H1/H2) dan **otomasi tanpa interaksi** (H4).
5. Dua hal yang harus diuji sebelum klaim apa pun: batas `plot_index` (H1) dan clamp `quantity` di sell (H3). Keduanya butuh akun alt + sesi hidup.
