# Missions — kontrak API dari HAR `cryptocrops.net.-MissionClaim.har`

Sumber: HAR rekaman halaman `/missions/` (57 entry, 3 endpoint API).
Dipakai untuk fitur klaim misi otomatis di `client.tick()`.

## Endpoint

```
POST /api/missions/claim
content-type: application/json
referer: https://cryptocrops.net/missions/

{"idempotency_key":"0d79d2b5-e30e-4341-9a29-4e9beefc7d72",
 "mission_id":"daily-faucet-coins-200"}
```

Respons `200`:

```json
{"claimed":{"mission_id":"daily-faucet-coins-200",
            "period":"daily",
            "pass_xp_earned":80,
            "harvest_pass_xp":190,
            "fertilizer_rarity":"",
            "fertilizer_quantity":0,
            "fertilizer_quantity_after":0,
            "claimed_at":1792523302652}}
```

Tidak ada endpoint "list misi" terpisah — daftar misi ikut di `GET /api/bootstrap`
pada `farm.missions`.

## Bentuk item misi (bootstrap)

```json
{"mission_id":"daily-harvest-5","period":"daily","metric":"harvests",
 "icon":"🥕","title":"Morning Harvest","description":"Harvest 25 mature crops…",
 "progress":25,"target":25,"unit":"count","pass_xp":40,
 "fertilizer_rarity":"common","fertilizer_quantity":1,
 "complete":true,"claimed":true,"claimed_at":1792508248508,
 "resets_at":1792540800000}
```

Field yang dipakai automation:

| field | arti |
|---|---|
| `mission_id` | dikirim balik ke `/api/missions/claim` |
| `complete` | progres sudah mencapai `target` |
| `claimed` | sudah diklaim di siklus ini (`resets_at` = waktu reset) |
| `pass_xp` | hadiah Harvest Pass XP (dibalas sebagai `pass_xp_earned`) |
| `fertilizer_rarity` / `_quantity` | hadiah tambahan (kadang `null`/`0`) |

## Siklus reset

- daily: `resets_at` = 1792540800000 (00:00 UTC berikutnya)
- weekly: `resets_at` = 1792972800000 (Senin 00:00 UTC)

14 misi per siklus: 7 daily + 7 weekly. Beberapa misi tidak bisa diselesaikan
bot (offerwall, shortlink, PTC) karena butuh interaksi manusia — automation
hanya mengklaim yang `complete`.

## Implementasi

`client.py`

```python
api.missions()        # list misi dari state bootstrap
api.missions_ready()  # complete and not claimed
api.claim_mission("weekly-harvest-25")
```

`client.tick()` sekarang punya langkah terakhir: setelah harvest/sell/order/plant,
state di-refresh lalu semua misi `ready` diklaim (bisa dimatikan dengan
`do_missions=False` / `autofarm.py --no-missions`).

Contoh hasil nyata:

```
misi Full Fields +150 pass xp · misi Produce Merchant +200 pass xp
```

## Catatan teknis

- Klaim memakai `idempotency_key` uuid4 baru tiap request; klaim ulang misi yang
  sama dijawab error (`ALREADY_CLAIMED`) dan diabaikan automation.
- `referer` harus `/missions/` — kalau tidak, server bisa menolak (403).
- Bootstrap ikut mengirim `farm.harvest_pass` (`free_rewards_claimable`) tapi
  endpoint klaim reward pass tidak terekam di HAR ini, jadi belum diotomasi.
