# CryptoCrops — Leveling & Progression (dari HAR #1 + #2)

Sumber: `farm.farm_progression`, `farm.harvest_pass`, `farm.seeds[].level/mastery_*`, `catalog.seeds[]`, `season.divisions`.
Semua angka di bawah dibaca dari payload, bukan tebakan. Yang ditandai *(hipotesis)* belum terverifikasi.

---

## 0. Ada EMPAT track terpisah — jangan dicampur

| Track | Progress | Naik dari | Efek |
|---|---|---|---|
| **Farm Level** | `farm_progression.xp` | panen, order, sponsored coins | **slot plot** + **seed level cap** |
| **Seed Level** | `seeds[].level` | belum teramati | poin per panen (diduga) |
| **Mastery** | `seeds[].mastery_*` | jumlah panen seed itu | bonus poin flat |
| **Harvest Pass** | `harvest_pass.xp` | jual produce, order | reward musiman (50 tier) |
| *(bonus)* **Divisi** | `league.total_points` | poin pool | bonus coin 0–1800 bps |

---

## 1. Farm Level — satu-satunya yang penting

### 1.1 Sumber XP (dari `xp_sources`)

```json
{"harvest": 5, "orderCompleted": 25, "sponsoredCoinsPerXp": 10}
```

- **panen = +5 xp** — terverifikasi: dua panen radish → `farm_xp_earned: 5`, lalu `farm_xp: 10`.
- **order selesai = +25 xp** — 5× nilai satu panen.
- **sponsored coins = 1 xp per 10 coin** *(hipotesis baca field)*.

Catatan penting: **5 xp itu flat, tidak tergantung nilai poin panen.** Radish 11 poin = 5 xp. Kalau pola ini konsisten ke semua seed, maka seed cepat selalu lebih baik untuk xp daripada seed mahal. *(belum diuji pada seed lain — ini satu-satunya unknown yang bisa membalik strategi)*

### 1.2 Kurva level (kumulatif xp)

| Lvl | XP total | ΔXP | seed cap | max plot |
|-----|---------:|----:|---------:|---------:|
| 1 | 0 | – | 2 | 4 |
| 2 | 250 | 250 | 3 | 6 |
| 3 | 750 | 500 | 4 | 8 |
| 4 | 1.500 | 750 | 5 | 10 |
| 5 | 3.000 | 1.500 | 6 | 12 |
| 6 | 5.500 | 2.500 | 7 | 14 |
| 7 | 9.000 | 3.500 | 8 | 16 |
| 8 | 14.500 | 5.500 | 9 | 18 |
| 9 | 22.000 | 7.500 | **10 (cap)** | 20 |
| 10 | 33.000 | 11.000 | 10 | 22 |
| **11** | **48.000** | 15.000 | 10 | **24** |
| 12 | 68.000 | 20.000 | 10 | 24 |
| 13 | 95.000 | 27.000 | 10 | 24 |
| … | … | … | 10 | 24 |
| 50 | 25.267.000 | – | 10 | 24 |

Setelah **L11 semua bonus mekanik berhenti** — plot 24, seed cap 10. L12–L50 murni badge/kosmetik (L50 = "Maximum Farm Level badge").

### 1.3 Estimasi waktu (radish 5 menit, 5 xp, plot = cap level)

| Dari → ke | ΔXP | plot | xp/jam | jam |
|---|---:|---:|---:|---:|
| 1 → 2 | 250 | 4 | 240 | 0,7 |
| 2 → 3 | 500 | 6 | 360 | 1,0 |
| 3 → 4 | 750 | 8 | 480 | 1,3 |
| 4 → 5 | 1.500 | 10 | 600 | 2,1 |
| 5 → 6 | 2.500 | 12 | 720 | 3,0 |
| 6 → 7 | 3.500 | 14 | 840 | 3,7 |
| 7 → 8 | 5.500 | 16 | 960 | 5,1 |
| 8 → 9 | 7.500 | 18 | 1.080 | 6,3 |
| 9 → 10 | 11.000 | 20 | 1.200 | 8,3 |
| 10 → 11 | 15.000 | 22 | 1.320 | 10,4 |
| **total L1 → L11** | 48.000 | – | – | **±42 jam** |
| L1 → L50 | 25,27 jt | 24 | 1.440 | **±17.555 jam (±2 tahun)** |

Artinya: target realistis = **L11**, lalu berhenti peduli level. L50 bukan design intent, itu tail kosong.

---

## 2. Hambatan sebenarnya: coin, bukan XP

`levels[].max_crop_plots` hanya **plafon**. Plot fisik dibeli lewat `capacity_upgrade` dengan **farm coins**:

```json
{"current_base_capacity":4,"next_base_capacity":5,"price":1000,
 "required_farm_level":2,"max_base_capacity":24,"affordable":false,
 "farm_coin_balance":0}
```

- butuh **L2** sebelum upgrade pertama bisa dibeli,
- harga pertama **1.000 coin**, dan `farm_coins` = 0.

Sumber coin: faucet 10/claim, order `base_coin_reward` 6–15, misi (mission `pass_xp` bukan coin), offerwall/shortlink/ptc.

Jadi urutannya: **L2 (1 jam) → kumpulkan 1.000 coin (±100 claim faucet / ±100 order) → plot 5**. Level membuka langit-langit, coin membeli lantainya. XP cepat tidak menolong kalau coin kosong — ini bottleneck desain yang sebenarnya.

---

## 3. Seed Level & Mastery

`seeds[]` per seed: `{quantity, level, mastery_level, mastery_harvests, mastery_progress}`.

- **seed level cap** naik dari farm level: L1→2, L2→3, … L9→10. Efek pastinya belum teramati (diduga menaikkan `pre_fresh_points` per panen).
- **mastery** berbasis jumlah panen seed itu:

| seed | `mastery_base_harvests` | `mastery_flat_points` |
|---|---:|---:|
| radish | 25 | +1 |
| lettuce | 25 | +1 |
| carrot | 15 | +1 |
| wheat | 8 | +2 |
| flashbloom | 25 | +10 |

Terbukti di response harvest: `mastery_harvests: 1` lalu `2`, `mastery_progress` mengikuti, `mastery_level: 0`. Jadi setiap 25 panen radish → mastery level +1 → +1 poin flat per panen.

Konsekuensi: **radish adalah seed terbaik untuk grind mastery** (25 panen = 2 jam, bonus +1 poin permanen) sekaligus terbaik untuk xp/jam. Wheat naik mastery 3× lebih cepat (8 panen) tapi grow 60 menit.

---

## 4. Harvest Pass (musiman, terpisah dari farm level)

```json
{"season_id":"harvest-pass-2026-10","season_name":"Haunted Circuit",
 "xp":0,"level":0,"current_level_xp":0,"next_level_xp":50,
 "xp_sources":{"produceSold":0,"orderCompleted":20},
 "season": 2026-10-01 → 2026-11-01}
```

- 50 tier, **total 9.000 xp** untuk selesai.
- Tier 1–10: 50, 125, 225, 350, 500, 700, 950, 1250, 1600, 2000.
- Tier 11–50: **linear +175** per tier (2175, 2350, … 9000).
- Reward free: 19 fertilizer, 16 coins, 10 farm_xp, 4 cosmetic, 1 seed.
- Reward premium: 15 cosmetic, 15 fertilizer, 9 farm_xp, 9 coins, 1 seed, 1 bundle (`haunted-circuit-finale`).

XP pass didapat dari **menjual produce** dan **menyelesaikan order (+20)**. Di capture, jual 22 poin menghasilkan `pass_xp_earned: 0` — jadi ada ambang minimum per penjualan, atau poin pass dihitung per unit/kelipatan *(hipotesis)*.

---

## 5. Divisi musim (bonus coin, bukan level)

| Divisi | Poin | bonus |
|---|---:|---:|
| Seedling | 0 | 0 bps |
| Farmhand | 100.000 | 200 bps |
| Cultivator | 500.000 | 500 bps |
| Harvester | 1.500.000 | 800 bps |
| Homesteader | 4.000.000 | 1.200 bps |
| Cropmaster | 10.000.000 | 1.800 bps |

Dengan 576 poin/jam di 4 plot: Farmhand = **174 jam** nonstop. Dengan 24 plot dan seed mythic (2.000+ poin/jam/plot), baru masuk akal. Divisi adalah end-game dari kepemilikan seed, bukan dari grinding.

---

## 6. Seed ladder — kenapa leveling berhenti terasa penting

Poin/jam per plot dari katalog (66 seed):

| kelas | contoh | poin/jam/plot |
|---|---|---:|
| starter | radish / lettuce | 144 |
| mid | wheat / potato / turnip | 120 / 114 / 108 |
| rare | blueberry / cranberry / sugarcane | 396 / 396 / 364 |
| epic | flashbloom / starfruit / voidberry | 2.048 / 606 / 1.876 |
| mythical | bloodmoon-pomegranate / celestial-bloom | 2.150 / 1.620 |

Lonjakan besar ada di **rare ke atas** (2,7×) dan **epic/mythical** (14×). Seed itu didapat dari `coin_price` (26.000–300.000 coin), harvest pass, atau drop — bukan dari level. Jadi throughput akhir ditentukan **seed yang dimiliki**, sedangkan level cuma memberi slot untuk menanamnya.

---

## 7. Ringkas: apa yang harus dikejar

1. **L2** — 250 xp = 50 panen radish ≈ 1 jam. Buka upgrade kapasitas.
2. **1.000 coin** — ini yang nyata menahan. Faucet + order + offerwall.
3. **L11** — 48.000 xp ≈ 42 jam nonstop; setelah ini level tidak memberi apa pun.
4. **Mastery radish** — 25 panen → +1 poin flat, permanen, murah.
5. **Seed rare/epic** — satu-satunya lompatan throughput nyata (2,7×–14×).
6. **L50 / Cropmaster** — tidak realistis (17.555 jam / 10 juta poin). Abaikan.

## 8. Unknown yang harus diuji

- apakah `farm_xp_earned` **flat 5** untuk semua seed, atau proporsional ke `pre_fresh_points`? (menentukan: radish vs wheat untuk xp)
- efek konkret `seed level` 2..10 terhadap poin panen
- formula `pass_xp` dari penjualan (kenapa 22 poin = 0 pass xp)
- `sponsoredCoinsPerXp: 10` — arah konversinya
- apakah `xp` order dihitung per order atau per syarat terpenuhi
