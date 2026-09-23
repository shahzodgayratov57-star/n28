# USD/UZS Rate Tracker

Kunlik AQSH dollari (USD/UZS) Markaziy bank kursini bank.uz'ning kurslar arxividan (`bank.uz/uz/currency/archive/kun-oy-yil`) tortib oladi, `data/usd_rates.csv` faylida tarixni saqlaydi, so'nggi 1 yillik grafikni (`charts/usd_last_year.png`) chizadi va Telegram bot orqali yuboradi.

## Fayllar

- `scripts/usd_tracker.py` — asosiy skript (`backfill`, `update`, `chart`, `send`, `daily` buyruqlari)
- `data/usd_rates.csv` — kunlik kurslar tarixi (sana, kurs)
- `charts/usd_last_year.png` — so'nggi yaratilgan grafik
- `config/telegram.json` — bot token va chat_id (**repo private saqlansin**)

## Kunlik ishga tushirish

```
pip install -r requirements.txt
python scripts/usd_tracker.py daily
```

Bu buyruq: eng so'nggi kunlik kursni oladi -> CSV'ga qo'shadi -> grafikni qayta chizadi -> Telegram'ga yuboradi.

Bu repo Claude'ning bulutli rejalashtirilgan agenti (routine) orqali har kuni avtomatik ishga tushiriladi.
