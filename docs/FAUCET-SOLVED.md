# Faucet claim — jalur yang berhasil

Status: **berhasil, terverifikasi dua kali** (claim #3 dan #4, saldo 30 → 40 coin).

## Kontrak server (tidak berubah dari HAR)

```
POST /api/earn/faucet-challenge   {}                     -> challenge_id, captcha{site_key},
                                                            verification{site_key, action, cdata, ticket}
POST /api/earn/faucet             {idempotency_key, faucet_challenge,
                                   captcha_token, captcha_ticket}
                                  -> {claimed, claim_id, total_coins, farm_coin_balance,
                                      farm_xp_earned, farm_xp, next_claim_at}
```

`captcha_ticket` = base64(payload) + "." + cdata, cdata = HMAC server. Tidak bisa dihitung sendiri,
jadi token Turnstile **wajib** dibuat dalam sesi yang sama dengan challenge tersebut.

## Kenapa jalur lain gagal

| pendekatan | hasil | penyebab |
|---|---|---|
| Chromium (patchright, Chrome sistem, headless & headed) | widget tidak pernah selesai | error `600010`, console "No available adapters", CSP memblokir iframe `data:,` |
| Turnstile-Solver di :5000 (implicit→explicit render) | token 816–858 char, tapi ditolak | token dibuat di luar origin/sesi situs → `FAUCET_CAPTCHA_FAILED` |
| Camoufox + halaman asli | **diterima** | situs sendiri memanggil `turnstile.render({cData})`, token lahir di context yang benar |

WebGL bukan penyebab: `gpu_probe.py` menunjukkan WebGL2 jalan di semua kombinasi Chromium
(NVIDIA GTX 1650 SUPER lewat ANGLE/D3D11).

## Tiga detail yang menentukan

1. **Klik kotak centang Turnstile.** Widget pakai managed mode, butuh interaksi.
   Kotak berada di bawah lipatan → `scrollIntoView({block:'center'})` dulu, baru hitung
   `getBoundingClientRect()`, gerakkan mouse manusiawi, klik di `(x+24, y+h/2)`.

2. **Klik tombol claim lewat JS.** Tombol tertutup overlay transparan
   (`div[data-format="3"]`, id `cc-…`), jadi `page.click()` kena "intercepts pointer events"
   dan timeout 15 s. `b.click()` langsung masuk ke handler situs.

3. **Jangan andalkan DOM untuk tahu token.** Token dibaca dari
   `input[name=cf-turnstile-response]` (752 char), tapi kalau kosong pun tidak masalah:
   yang penting tombol sudah `enabled` atau status captcha "Verified". Handler situs
   menyimpan token di closure-nya sendiri.

## Alur final (`camoufox_claim.py`)

```
goto /faucet/  ->  tunggu [data-claim-faucet] (reload sekali kalau interstitial)
  ->  loop 700ms: satu evaluate baca {tombol, disabled, status captcha, token}
  ->  klik kotak captcha (maks 3x, jeda 7s)
  ->  berhenti saat token ada / tombol aktif / status "Verified"
  ->  b.click()  ->  tunggu response POST /api/earn/faucet (claim_id / error)
  ->  kalau tab keburu tutup: faucet_run.py verifikasi lewat bootstrap (claim_count naik)
```

Rate limit yang harus dihormati:
- `/faucet-challenge` ~60 s per klaim
- `FAUCET_RATE_LIMITED` bisa lebih panjang (pernah 769 s)
- satu window klaim = satu challenge; memanggil challenge lagi menerbitkan cdata baru
  dan **membatalkan** token yang lama

## Pemakaian

```powershell
cd C:\Users\Admin\.config\opencode\agents\cryptocrops-har
python faucet_run.py            # countdown + klaim otomatis sekali (headed)
python faucet_run.py --headless # sama, tanpa jendela — TERBUKTI JALAN
python faucet_run.py --loop     # ikut cooldown terus
python faucet_run.py --json     # satu baris JSON
python autofarm.py --headless   # checkpoint -> faucet -> harvest/sell/plant
```

Headless terverifikasi pada claim #6 (`18d17f9c…`, saldo 60): widget verified 10 s
setelah klik kotak, token 752 char, tombol aktif, klaim diterima. Jadi Cloudflare
di situs ini tidak menolak Firefox headless.

`faucet_run.py` otomatis pindah ke interpreter yang punya camoufox lengkap
(env `CC_PY`, default `%TEMP%\opencode\Turnstile-Solver\.venv\Scripts\python.exe`).
Kalau biner belum di-fetch: `camoufox fetch`.

Catatan: jangan tutup jendela Firefox selama klaim berjalan (≈40–60 s setelah widget hijau).
