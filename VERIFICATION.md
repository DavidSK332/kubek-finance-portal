# Overenie opravenej verzie

Dátum: 18. 10. 2026. Lokálne prostredie: Windows, Python 3.12.14, samostatné virtuálne prostredie.

## Automatizované testy

Úspešne overených bolo 87 testov. Po doplnení hlavičky `User-Agent` pre Resend opakovane prešlo všetkých 36 testov služieb.

| Oblasť | Počet a rozsah |
|---|---|
| Konfigurácia | 16; produkčné nastavenie, šifrovací kľúč, kontakt bez adresy a povolení hostitelia |
| Výpočty | 15; nulový príjem/úrok, refinancovanie a validácia vstupov |
| Webové routy | 20; HTTPS/CSRF, oddelenie agentov, nemenné sumarizácie a bezpečné opakovanie úloh |
| Worker, AI, PDF a e-mailové adaptéry | 36; súhlas s AI, spracovanie na pozadí, SMTP/SendGrid/Resend, PDF prílohy, idempotencia a chyby doručenia |

Testy používajú dočasnú SQLite databázu a simulujú externé API. Skutočné doručenie e-mailu bolo overené osobitne v produkcii, ako je uvedené nižšie. Validácia šifrovacieho kľúča jeho hodnotu nemení ani automaticky negeneruje novú.

## Aktuálne nasadenie

[portal.kubekfinance.sk](https://portal.kubekfinance.sk) používa platný HTTPS certifikát a vzhľad podľa `kubekfinance.sk`. Prihlásenie, `/healthz` aj `/static/brand.css` vrátili HTTP 200. Vzhľad bol skontrolovaný na počítači aj pri mobilnej šírke. Hlavný web `kubekfinance.sk` a `www` zostali zachované.

Všetky štyri služby — web, worker, PostgreSQL a Redis — sú online; Railway pri kontrole nehlásil problém. Web aj worker úspešne nasadili commit `dd6faf7375e33f162810063128e11737a01a12b9`.

- Web: deployment `ac2b96bf-441c-4d93-b158-549598a06a4c`, stav `SUCCESS`.
- Worker: deployment `f63eb9a7-566f-4a57-ad2e-bf20a7f22572`, stav `SUCCESS`.

Primárny kontakt a e-mail agenta sú `info@kubekfinance.sk`. Prevádzkovateľ je Dávid Kubek, IČO `55012469`, DIČ `2121841821`; adresa sa nezobrazuje ani nevyžaduje. Každý agent vidí vlastné dopyty. Aktuálny používateľov účet obsahuje jeden dopyt. Jeho pôvodná blokovaná notifikácia bola zopakovaná cez rozhranie a worker ju dokončil.

## E-mail a AI

Web aj worker používajú `EMAIL_BACKEND=resend` a odosielateľa `info@kubekfinance.sk`. Kľúč je nastavený v Railway, nie v zdroji ani tomto dokumente. Doména odosielateľa je v Resende overená. Nastavené sú:

- TXT `resend._domainkey` s verejným podpisovým kľúčom.
- CNAME `send` → `send.forge.rmta.net`.
- CNAME `rsend` → `rsend-euw1.forge.rmta.net`.

Obnovené boli aj MX záznamy Websupportu: `mx10.websupport.sk` s prioritou 10 a `mx20.websupport.sk` s prioritou 100, spolu so SPF záznamom. Odosielanie používa HTTPS API Resendu.

Skutočný testovací e-mail bez klientskych údajov na `info@kubekfinance.sk` má v Resende stav **delivered**. Referencia: `01a14edc-3bfc-72b6-b08b-05f0fe40c7eb`. Následné živé volanie cez adaptér aplikácie s rovnakým idempotentným kľúčom vrátilo tú istú referenciu bez duplicitnej správy. Adaptér má vlastnú hlavičku `User-Agent` a rozlišuje odmietnutie od neistého výsledku doručenia. Dokončené e-maily sa automaticky neposielajú opakovane.

Pôvodná blokovaná úloha `notify_agent` č. 6 patriaca agentovi `info@kubekfinance.sk` bola zopakovaná cez portál a má stav `done`. Resend pri notifikácii s referenciou `01a14ee2-7227-79d2-9b49-a762dcea1091` potvrdil stav **delivered**. Doručenie testovacej správy aj pôvodnej notifikácie bolo overené v rozhraní Resendu; produkčná administrátorská konzola bola po overení zatvorená.

`OPENAI_API_KEY` aj model `gpt-4o-mini` sú nastavené v oboch službách. AI je momentálne blokovaná kreditom poskytovateľa: živé volanie vrátilo HTTP 429, kód `credit_balance_exhausted`, a opakovanie pôvodnej úlohy č. 5 s uloženým súhlasom opäť skončilo `RateLimitError`. Fakturačná stránka organizácie „Test“, ku ktorej patrí aktívny kľúč, stále ukazuje `Free trial`, zostatok `$0.00` a možnosť `Add payment details`. Používateľ dostal presnú stránku na doplnenie kreditu; jeho predchádzajúce potvrdenie sa zatiaľ v tomto účte neprejavilo. Úspešnú AI analýzu treba potvrdiť po dostupnosti kreditu. Kľúč nechýba a konfigurácia je nastavená. Klientske údaje sa na AI posielajú iba pri uloženom súhlase.

## Predchádzajúce živé overenie

Po pôvodnej oprave úspešne prešli odoslanie päťkrokového formulára, uloženie fiktívneho dopytu do PostgreSQL, spracovanie workerom a vytvorenie platného PDF s veľkosťou 47 759 bajtov. Bez súhlasu s AI mala analýza správne stav `skipped`. V čase tohto historického testu boli e-maily vypnuté; tento stav už neopisuje aktuálne nastavenie Resendu.

Opravy odstránili neplatný zápis šifrovacieho kľúča, neúplný obsah repozitára a konflikt `Referrer-Policy: no-referrer` s HTTPS kontrolou Flask-WTF. Aktuálne `same-origin` zachováva CSRF token aj kontrolu pôvodu. Docker štart vytvorí databázovú schému pred webom. Používateľ vytvoril prihlasovací účet priamo v Railway konzole; heslo nie je súčasťou projektu ani záznamov.

Lokálny Docker build ani úplný automatizovaný integračný test PostgreSQL/Redis neprebehli. Cloudový Docker build, štart služieb a uvedené živé kontroly prebehli v Railway a Chrome. Úplný produkčný postup uloženia návrhu a odoslania klientskej sumarizácie s PDF zatiaľ nebol potvrdený; automatizované testy ho pokrývajú so simulovaným odoslaním.

## Fiktívny výpočtový príklad

Príjem 3 000 EUR, bežné výdavky 1 200 EUR, dva dlhy spolu 90 000 EUR a splátky 630 EUR. DTI 2,50; pomer splátok k príjmu 21 %; zostatok 1 170 EUR.

Modelové refinancovanie 90 000 EUR pri 3,6 % na 25 rokov má splátku 455,40 EUR. Pri nových pravidelných nákladoch 20 EUR mesačne je zostatok 1 324,60 EUR a jeho zlepšenie 154,60 EUR mesačne. Ide o vymyslenú ponuku, nie aktuálnu sadzbu konkrétnej banky ani preukázanú celkovú úsporu.
