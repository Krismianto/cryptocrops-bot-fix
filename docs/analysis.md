# CryptoCrops.net — Bedah HAR (Web Game)

**Sumber:** `C:\Users\Admin\Downloads\cryptocrops.net.har`
**Ukuran:** 20,262,446 byte · HAR 1.2 · `creator: WebInspector 537.36` (Chrome DevTools export)
**Isi:** 108 entry · 23 page (SPA navigation) · 1 sesi login `SawitDES`
**Tanggal capture:** 2026-10-20 07:23:43Z → 07:26:17Z (≈2 m 34 s)
**REA evidence:** `ev_c64c739b6bc26058fddbfb8da76618dbfd14dee3d5da15e8c4f6a7a4244c2972`,
`ev_5d9c4e3aadcd24bf7a547fbef892157e2ef29127b3a59e81253ea8ab3f5b3601`
(adapter `har-schema/lossless-json` · har-schema@2.0.0 · jsonc-parser@3.3.1 · lossless-json@4.3.1)

---

## 0. Catatan integritas capture (penting sebelum analisis)

HAR asli **tidak valid** menurut schema HAR 1.2 sehingga ditolak REA dua kali:

| Masalah | Detail | Dampak |
|---|---|---|
| `serverIPAddress` | `"[2606:4700:3031::6815:2acd]"` — IPv6 dibungkus bracket | REA: `invalid_format` di `/log/entries/0/serverIPAddress` |
| Body 4.9 MB | `male.glb` base64 6.59 MB | Decoder REA `RangeError` (seluruh capture gagal, bukan partial) |
| `content.text: null` | Hasil normalisasi awal | REA: `type` invalid — properti harus dihilangkan, bukan null |

**Perbaikan yang dilakukan (file asli tidak disentuh):**
`%TEMP%\opencode\cryptocrops\normalized.har` (IPv6 di-unbracket) → `light.har` (body >1 MB dihapus, `content.size` dipertahankan).
sha256 `light.har` = `68c7b37b9514bc06fa015d49fe0b2587f59edc7be40df6fbb52f84409580b93c`.

**Kesimpulan capture:** HAR ini hanya menangkap *read paths* + 2 write path. **Tidak ada** cookie, header `Authorization`, `Set-Cookie`, CSRF token, maupun request login — exporter Chrome men-strip cookie, jadi sesi tidak bisa direplay apa adanya dari file ini.

---

## 1. Arsitektur

```
Browser (Next.js SPA, 23 route)  ──HTTPS──►  Cloudflare  ──►  origin API (JSON)
        │                                        │
        ├─ /googletag/ga/g/c  (GA4 proxy same-origin, G-2H4HRF6D77)
        ├─ cdn.ccnsad.com/get/v (ad network, CORS *))
        └─ /admin/farmer-assets/v1/male.glb (4.94 MB, publik, CF-cache HIT)
```

Fakta dari header:

- `server: cloudflare`, `cf-ray: …-KIX` / `-HKG`, `alt-svc: h3=":443"`.
- Security header origin: `content-security-policy: frame-ancestors 'self'; object-src 'none'; base-uri 'self'`, `strict-transport-security`, `x-content-type-options: nosniff`, `referrer-policy: strict-origin-when-cross-origin`, `permissions-policy: browsing-topics=(), usb=(), serial=()`.
- `cache-control: no-store` pada API (benar) **dan** pada GLB — tapi `cf-cache-status: HIT` pada GLB ⇒ rule "cache everything" menimpa `no-store`.
- Tidak ada header rate-limit (`x-ratelimit-*`, `retry-after`) di satu pun response.

**Stack indikasi:** Next.js `app/` router (URL berakhiran `/farm/`, `/pools/` …), API JSON snake_case + beberapa camelCase (pool/season) ⇒ campuran service (Next API route + backend terpisah). ID memakai UUIDv4; waktu memakai epoch-ms.

---

## 2. Peta endpoint (bukti ordinal HAR)

| # | Method | Path | Status | Size | Body |
|---|---|---|---|---|---|
| 0,5,8,…(29×) | GET | `/api/bootstrap` | 200 | 127.5–129.1 KB | snapshot state penuh |
| 1,…(23×) | GET | `/api/catalog?version=6` | 200 | 21,775 | 66 seed def |
| 2,…(13×) | GET | `cdn.ccnsad.com/get/v?u=…&m=0&hw=1&n=…` | 200 | 237 | iklan HTML |
| 3,78 | GET | `/admin/farmer-assets/v1/male.glb` | 200 | 4,941,920 | glTF binary |
| 40,45 | GET | `/api/guilds` | 200 | 13,682 | directory + tasks + event |
| 54 | GET | `/api/leaderboards` | 200 | 13,906 | pool/season/likes/collection/mastery |
| 59 | GET | `/api/referrals` | 200 | 342 | kode + statistik |
| 64 | GET | `/api/community?mode=top` | 200 | 9,677 | feed |
| 69 | GET | `/api/withdrawals` | 200 | 652 | kanal payout |
| 74 | GET | `/api/auth/account` | 200 | 577 | akun + sesi |
| 80,82,84 | POST | `/api/homestead/companions/action` | 200 | ~20.4 KB | narrative step |
| 86,88,90,92 | POST | `/api/farm/plant` | **201** | 189 | tanam benih |
| 94 | GET | `/api/chat/context` | 200 | 14 | `{"guild":null}` |
| 98 | GET | `/api/pools` | 200 | 5,521 | pool + history |
| 4,7,…(25×) | POST | `/googletag/ga/g/c` | 204 | 0 | GA4 beacon |

**Tidak tertangkap (gap analisis):** login/signup, `harvest`, `sell`, `faucet/claim`, `farm/checkpoint`, `shop/*`, `orders/*`, `missions/claim`, `pass/claim`, `guild/*` write, `withdraw/*` write, `premium/*`. Semua kesimpulan soal endpoint itu di laporan ini ditandai **inferensi UI**, bukan bukti HAR.

### Bentuk request write (verbatim)

```http
POST /api/farm/plant
content-type: application/json
origin: https://cryptocrops.net
referer: https://cryptocrops.net/farm/

{"idempotency_key":"591cb2b4-2dc2-4810-b4ab-e0600cf4da02","seed_id":"carrot","plot_index":1}
→ 201 {"planted":{"crop_id":"ce5903e2-…","plot_index":1,"seed_id":"carrot",
        "ready_at":1792482902007,"perfect_until":1792483352007,
        "pre_fresh_points":66,"yield_level":1}}

POST /api/homestead/companions/action
{"action":"narrative","pet":"intro","story_step":0,"idempotency_key":"7f088c32-…"}
→ 200 {"result":{"ok":true,"message":"Story continued."},"companions":{…}}
```

Karakteristik: **tanpa** header auth eksplisit, **tanpa** CSRF token, **tanpa** captcha pada plant, body JSON murni, idempotency key UUIDv4 dibuat client.

---

## 3. Model auth & sesi

`GET /api/auth/account`:

```json
{"account":{"userId":"08fa90ad-…","playerId":"4ab70b44-9d6e-402a-bc54-6c4953e78d2c",
 "email":"marioatmajanugrahaa@gmail.com","displayName":"SawitDES","role":"player",
 "status":"active","createdAt":1792480977255,"lastLoginAt":1792481003064,
 "emailVerified":true},
 "sessions":[{"session_id":"e026ae73-…","created_at":1792481003064,
 "expires_at":1795073003064,"last_seen_at":1792481003064,
 "user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) … Chrome/155.0.0.0",
 "current":true}]}
```

- `expires_at − created_at = 2,592,000,000 ms = 30 hari`. Sesi server-side (ID opaque), bukan JWT — tidak ada token yang terlihat di body.
- Akun dibuat 2.9 detik sebelum login terakhir ⇒ kemungkinan **signup+auto-login** dalam satu alur, `emailVerified:true` instan (tidak ada verifikasi email nyata).
- `role: player`, `can_manage_site:false`, `can_preview_farm:true` (flag preview farm = lihat farm orang lain?).
- HAR tidak menyimpan cookie ⇒ mekanisme pengangkut sesi **tidak terbukti**; secara arsitektur paling mungkin cookie `HttpOnly` (karena tidak ada header auth di JS request).

---

## 4. Skema state `/api/bootstrap`

Snapshot tunggal, dipanggil ulang di **setiap navigasi** (29×). Root key:

```
mode:"demo" · cxl_connected:false
auth{authenticated, player_id, email, display_name, role, can_manage_site, can_preview_farm}
player{display_name, premium, premium_until, linked_at}
pool{cycleId, startsAt, endsAt, harvestCredits, weather{code,name,emoji,bonusBps},
     creditsPerUsd, estimatedHarvestCredits, estimatedUsdMicros}
season{season_id, name, ends_at, divisions[6]}
security{faucet_enabled, turnstile_enabled, farm_checkpoint_enabled,
         farm_checkpoint_provider:"number_image", turnstile_site_key,
         farm_checkpoint_binding, faucet_captcha{provider,configured,mandatory,site_key}}
farm_announcement{active, message, updated_at}
farm{profile, seeds, crops, plot_upgrades[28], inventory, fertilizers[6],
     pool_progress, league, orders[8], order_rerolls, collection_book,
     harvest_pass[50 tier], missions[14], farm_progression[50 level],
     capacity_upgrade, faucet, auto_cropper, farm_checkpoint, server_now}
homestead{levels, placements[~250], trees[8], treeOwnershipVersion, benefits,
          max_level, farm_level, coins, premium_active, buildings, server_now,
          companions, builder, guild, decor, blueprints, landscaping,
          packs, owned_capacity, trees, decor_catalog, decoration_packs, next_land_cost}
```

Poin penting:

- **`mode:"demo"`** padahal `auth.authenticated:true` dan aksi menulis berhasil (201) ⇒ "demo" bukan read-only; kemungkinan penanda mode ekonomi/demo farm baru (Crypto Crops 2.0).
- `server_now` dikirim di 3 tempat ⇒ semua timer (grow/ready/perfect) bisa disinkronkan client, **tidak perlu** percaya jam lokal. Ini yang dipakai bot untuk hitung `ready_at`.
- `crops[]` memuat `planted_at`, `ready_at`, `perfect_until`, `pre_fresh_points`, `pool_cycle_id`, `weather_code`, `yield_level` ⇒ jendela "perfect" (bonus) = 450 s untuk carrot, 150 s lettuce/radish.
- `plot_upgrades` berisi **28 plot** walau `total_capacity:4` ⇒ client tahu seluruh grid; nilai `next_cost:5000`.
- `farm_checkpoint{required:false, next_challenge_at:1792482528910}` ⇒ challenge pertama ~24 menit setelah sesi mulai, provider `number_image` (captcha gambar angka).
- `security.turnstile_site_key = 0x4AAAAAAE8SO-yZVCky9wK7` (site key publik, dipakai faucet).

---

## 5. Ekonomi (angka nyata dari capture)

| Besaran | Nilai |
|---|---|
| Denominasi | `1 USD = 10,000 Harvest Credits (HC)` |
| Pool per cycle | `600,000 HC = $60` |
| Panjang cycle | `endsAt − startsAt = 21,600,000 ms = 6 jam` |
| Total points cycle berjalan (snapshot awal) | 1,305,651 |
| Total points cycle selesai (histori) | 7.77M – 12.77M |
| Eligible players per cycle | 815 – 1,151 |
| Payout nyata rata-rata | `600,000 / ~9.5M × points` ⇒ ≈ $0.06/player/6 jam |
| Withdraw FaucetPay | min **1 HC** (≈$0.0001) |
| Withdraw direct wallet | min **10,000 HC** (=$1), manual |
| CXL wallet | min 1,000 HC, instant, `linked:false` |
| Farm Coins | sumber: faucet (10 base), offerwall, shortlink, PTC, order, pass |
| Capacity upgrade | 1,000 coins → base 5 plot (butuh farm level 2) |

**Tabel seed teratas (poin/jam)** — dihitung dari `catalog`:

| seed | rarity | jam | pts | pts/jam | harga coin |
|---|---|---|---|---|---|
| bloodmoon-pomegranate | Mythical | 4 | 8,602 | 2,150.5 | cxl_shop |
| flashbloom | Mythical | 0.25 | 512 | 2,048 | cxl_shop |
| voidberry | Mythical | 0.5 | 938 | 1,876 | cxl_shop |
| chrono-clover | Mythical | 0.08 | 155 | 1,860 | cxl_shop |
| quantum-quinoa | Mythical | 0.75 | 1,279 | 1,705.3 | cxl_shop |
| celestial-bloom | Mythical | 6 | 9,719 | 1,619.8 | cxl_shop |
| infinity-melon | Mythical | 12 | 18,414 | 1,534.5 | cxl_shop |

**ROI coin terbaik (poin per 1,000 coin)** — jalur F2P:

| seed | jam | pts | coin | pts/1k coin |
|---|---|---|---|---|
| turnip | 12 | 1,296 | 2,200 | 589.1 |
| oats | 8 | 864 | 1,800 | 480.0 |
| yellow-onion | 6 | 684 | 1,500 | 456.0 |
| potato | 4 | 456 | 1,200 | 380.0 |
| green-beans | 2 | 240 | 900 | 266.7 |
| green-peas | 0.75 | 99 | 600 | 165.0 |

**Reality check payout:** untuk dapat $1 (10,000 HC) di pool 9.5M points butuh ~158,000 points ⇒ setara ~2,400 harvest carrot (66 pts) dalam 6 jam. Tidak feasible manual; pool memang didesain sebagai micro-reward. Yang realistis: farming poin untuk leaderboard/season, bukan profit.

**Season/league:** `league-2026-10-04`, divisi `Seedling→Cropmaster`, threshold 0 / 100k / 500k / 1.5M / 4M / 10M poin, bonus coin 0–1800 bps.

**Harvest Pass "Haunted Circuit"**: 50 tier, `xp` dari `produceSold` + `orderCompleted` (20 xp), tier 1 = 50 xp.

---

## 6. Anti-bot & integritas

| Kontrol | Bukti | Catatan |
|---|---|---|
| Cloudflare Turnstile | `security.turnstile_enabled`, `faucet_captcha.mandatory:true`, site key `0x4AAAAAAE8SO-yZVCky9wK7` | wajib di faucet, **tidak** di plant |
| Farm checkpoint | `provider:"number_image"`, `binding = player_id`, `next_challenge_at` | captcha gambar angka periodik; binding ke player ⇒ tidak bisa dipakai lintas akun |
| Idempotency key | UUIDv4 per request write | dedupe server-side; key dibuat client |
| Server time | `server_now` ×3 | anti clock-skew, memudahkan bot menghitung timer |
| Rate limit | **tidak ada header** | kemungkinan di Cloudflare (tidak terlihat) |

**Implikasi:** automasi tanam/harvest tidak menghadapi captcha, tetapi setiap ~20–25 menit akan muncul checkpoint `number_image` yang harus dipecahkan (OCR/Tesseract atau manual). Bila checkpoint gagal, `farm_checkpoint.required` menjadi `true` ⇒ aksi farm diblok (inferensi dari field `required/required_since`).

---

## 7. Permukaan uji (prioritas, semua butuh verifikasi live)

| # | Hipotesis | Dasar | Cara uji | Risiko |
|---|---|---|---|---|
| 1 | Plant di plot terkunci (`plot_index` 5–28) | `plot_upgrades` punya 28 entri, `total_capacity:4` | `POST /api/farm/plant {"plot_index":5}` | bila lolos: free extra plot |
| 2 | Race idempotency | key client-side, `201` idempoten | 2 request paralel, key sama & beda | dobel tanam / dobel seed |
| 3 | Skip narrative `story_step` | `story_step` dari client, server balas "Story continued" | kirim step 17 langsung | skip progres / reward journal |
| 4 | Seed tak dimiliki | `seed_id` dari client, `source_owned:false` ada di orders | tanam `infinity-melon` saat quantity 0 | item duplication |
| 5 | Replay plant dengan key lama + body baru | dedupe berbasis key | ganti `seed_id`, key lama | cache confusion |
| 6 | `/admin/*` static exposure | GLB publik + CF HIT walau `no-store` | enumerasi `/admin/farmer-assets/v1/*` | aset/endpoint internal bocor |
| 7 | Enumerasi `can_preview_farm` | flag di bootstrap | `?player=` / `preview` param | lihat farm orang lain |
| 8 | PII di bootstrap | `email`, `player_id` di setiap load | kombinasikan dgn XSS/CSRF | enumerasi akun |
| 9 | Withdraw abuse | 3 kanal payout, min 1 HC FaucetPay | uji double-submit `withdraw` | payout ganda (butuh capture endpoint) |
| 10 | Checkpoint bypass | `binding` = player_id | replay solve antar sesi | bot lolos deteksi |

Catatan: tidak ada bukti HAR bahwa 1–10 berhasil. Semuanya hipotesis berdasarkan *trust boundary* yang terlihat.

---

## 8. Privasi / pihak ketiga

- **Google Analytics 4** `G-2H4HRF6D77`, diproksi same-origin lewat `/googletag/ga/g/c` (anti adblock). Parameter membawa `cid`, `sid`, `_gsid`, `dl`, `dr`, `sr=1366x768`, `ul=id-id`, `ur=ID-JK`, plus `tag_exp` (server experiment flags).
- **CDN iklan** `cdn.ccnsad.com` — `u=8cdac44de0f4973a` (ID publisher/slot), `hw=1`, `m=0`, `n=<random>`; response `access-control-allow-origin: *`, isi `<div class="adbytes-display-ad">` + `adbytes.media/js/show_ads.js` (728×90).
- **CXL** eksternal (`cxlgames.com`): `cxl_connected:false`, seed premium `acquisition:"cxl_shop"`, paket dekorasi $9.99–$19.99, `team_slot_price_usd_cents:3500`.
- Lokasi/waktu user terbaca `ID-JK`, `id-ID`; UA Chrome 155 (build tidak lazim → kemungkinan spoof/driverless, layak dicatat).

---

## 9. Kualitas / efisiensi (temuan engineering)

1. `bootstrap` 29× per sesi 2.5 menit (~127 KB/response, ±3.7 MB) tanpa `ETag`/`If-None-Match` → payload dominan, padahal 80% statis (`plot_upgrades`, `farm_progression`, `harvest_pass`, `missions`, `decor_catalog`).
2. `male.glb` 4.9 MB di-load 2× dalam satu sesi (farm → account → farm) = 9.88 MB; `cache-control: private,no-store` menandakan developer sadar, tapi Cloudflare tetap HIT.
3. `catalog?version=6` tetap di-fetch 23× (tiap route) — cache client tidak dipakai maksimal.
4. `content.type` campur snake_case/camelCase (`cycleId` vs `cycle_id`, `startsAt` vs `starts_at`) → indikasi dua backend di belakang satu domain.
5. `chat/context` mengembalikan `{"guild":null}` 14 byte, dipanggil walau tidak ada guild.
6. Emoji ter-encode rusak (`dYOO`, `dY��`) pada beberapa field → double-encoding UTF-8 di layer API (kosmetik, tapi menyulitkan parsing nama).

---

## 10. Checklist capture lanjutan (supaya analisis tuntas)

Rekam ulang dengan DevTools **Preserve log** + opsi cookie tidak di-strip (atau pakai mitmproxy), lalu lakukan:

1. Login/signup (dapatkan alur auth + cookie).
2. `harvest` satu crop → dapatkan endpoint + formula poin.
3. `sell` produce → `produceSold` (pass xp).
4. `faucet/claim` (Turnstile) → body token + validasi.
5. Biarkan 25 menit → `farm/checkpoint` (number_image) → struktur challenge + submit.
6. `shop` beli seed/plot, `orders` complete, `missions/claim`, `pass/claim`.
7. `withdraw` FaucetPay 1 HC → validasi double-submit.
8. Guild: create/join/donate.

Target evidence: 1 HAR per alur, ukuran <30 MB (batas REA 32 MiB), body >1 MB dipisah.

---

## 11. Ringkasan satu paragraf

CryptoCrops 2.0 adalah SPA Next.js di balik Cloudflare dengan satu endpoint snapshot (`/api/bootstrap`, ±128 KB) yang dipanggil di setiap navigasi, katalog 66 seed, dan 2 write-path yang tertangkap (`farm/plant`, `companions/action`) memakai idempotency key client-side tanpa CSRF token. Ekonomi: pool $60 per 6 jam dibagi proporsional ke ~1.000 pemain (rata-rata ~$0.06/cycle), 1 USD = 10.000 HC, withdraw mulai 1 HC via FaucetPay. Anti-bot berupa Turnstile (faucet) dan checkpoint captcha `number_image` tiap ~24 menit yang di-bind ke `player_id`. Permukaan uji paling menarik bukan captcha, tapi *trust boundary* di parameter client: `plot_index` sampai 28, `story_step` bebas, `seed_id` bebas, dan idempotency key yang bisa di-race.
