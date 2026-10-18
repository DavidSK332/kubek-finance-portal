# Overenie opravenej verzie

Dátum: 18. 10. 2026. Prostredie: Windows, Python 3.12.14, samostatné virtuálne prostredie.

| Kontrola | Výsledok |
|---|---|
| `python -m pytest -q` | Všetkých 43 testov úspešných |
| Neplatný alebo chýbajúci `ENCRYPTION_KEY` | 4 regresné prípady; zrozumiteľná chyba bez vypísania hodnoty kľúča |
| Platná produkčná konfigurácia | HTTPS prihlasovacia stránka, bezpečnostné hlavičky a `/healthz` po vytvorení schémy úspešné |
| HTTPS formulár a CSRF | Regresný test zachováva `Referrer-Policy: same-origin`; platný token a rovnaký pôvod prejdú, chýbajúci alebo cudzí Referer vracia 400 |
| Výpočty | 15 testov vrátane nulového príjmu/úroku, refinancovania a validácie vstupov |
| Webové routy | 11 testov vrátane skutočného CSRF tokenu, oddelenia agentov a nemenných sumarizácií |
| Worker, AI, PDF a e-mailové adaptéry | 11 testov; OpenAI a prenos SMTP/SendGrid simulované |

Automatizované testy používajú dočasnú SQLite databázu; živé overenie Railway je uvedené nižšie. Validácia šifrovacieho kľúča pôvodnú hodnotu nemení ani automaticky negeneruje novú.

## Stav nasadenia

Pri kontrole existujúceho nasadenia bol zistený neplatný `ENCRYPTION_KEY` a neúplný obsah GitHub repozitára bez priečinkov so šablónami, statickými súbormi a fontmi. Opravený zdroj obsahuje tieto súbory a návod používa nastavenia Railway dashboardu.

**Railway úspešne nasadil všetky štyri služby: web, worker, PostgreSQL a Redis.** Pri následnom živom teste HTTPS formulára sa objavila chyba 400: pôvodná hlavička `Referrer-Policy: no-referrer` bránila odoslaniu Referer potrebného na prísnu HTTPS kontrolu Flask-WTF. Oprava používa `same-origin` a zachováva kontrolu CSRF tokenu aj pôvodu; pribudol produkčný regresný test.

Živé overenie po oprave CSRF prešlo:
- Verejné HTTPS `/login`, `/healthz`, CSS a JavaScript vrátili HTTP 200.
- V prehliadači bol úspešne odoslaný päťkrokový formulár a zobrazené potvrdenie uloženia.
- PostgreSQL obsahuje fiktívny dopyt „TEST Overenie nasadenia“. Worker dokončil úlohu `analyze`; bez voliteľného súhlasu s AI je stav `skipped`.
- V produkčnom kontajneri sa z tohto dopytu vygenerovalo platné PDF s veľkosťou 47 759 bajtov.
- Notifikácia je očakávane `blocked`, pretože `EMAIL_BACKEND=disabled`. Nebol odoslaný skutočný e-mail ani vykonané živé OpenAI volanie.
- Používateľ vytvoril prihlasovací účet priamo v Railway konzole; heslo nie je súčasťou projektu ani overovacích záznamov.

Fiktívny dopyt zostal označený ako test pre kontrolu v dashboarde. Kompletný postup uloženia návrhu a odoslania sumarizácie v produkcii sa zatiaľ nevykonal; tieto scenáre pokrývajú automatizované testy. Podľa potreby zostáva doplniť API/e-mailové údaje.

Aktuálna úprava nastavuje primárny kontaktný e-mail na `info@kubekfinance.sk`, dopĺňa IČO `55012469` a DIČ `2121841821` a odstraňuje adresu prevádzkovateľa z aplikácie aj konfigurácie. Nasadenie bolo overené: stránka kontaktu aj prihlásenie vracajú HTTP 200, kontakt obsahuje obe identifikačné čísla a klikateľný e-mail; adresa sa nezobrazuje. Prihlásenie predvyplní info@kubekfinance.sk. Všetkých 6 kontrol konfigurácie prešlo bez adresy prevádzkovateľa. Všetky štyri služby sú online.

Lokálny Docker build, úplný automatizovaný PostgreSQL/Redis integračný test ani odosielanie skutočných správ neprebehli. Cloudový Docker build, štart služieb a vizuálna kontrola prihlasovacej stránky i odoslania dotazníka prebehli cez Railway a Chrome.

## Fiktívny výpočtový príklad

Príjem 3 000 EUR, bežné výdavky 1 200 EUR, dva dlhy spolu 90 000 EUR a splátky 630 EUR. DTI 2,50; pomer splátok k príjmu 21 %; zostatok 1 170 EUR.

Modelové refinancovanie 90 000 EUR pri 3,6 % na 25 rokov má splátku 455,40 EUR. Pri nových pravidelných nákladoch 20 EUR mesačne je zostatok 1 324,60 EUR a jeho zlepšenie 154,60 EUR mesačne. Ide o vymyslenú ponuku, nie aktuálnu sadzbu konkrétnej banky ani preukázanú celkovú úsporu.
