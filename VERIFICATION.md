# Overenie opravenej verzie

Dátum: 18. 10. 2026. Prostredie: Windows, Python 3.12.14, samostatné virtuálne prostredie.

| Kontrola | Výsledok |
|---|---|
| `python -m pytest -q` | Všetkých 53 testov úspešných |
| Konfigurácia | 16 testov vrátane produkčného nastavenia, kontaktu bez adresy a povolených hostiteľov |
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

Predchádzajúce živé overenie po oprave CSRF prešlo:
- Verejné HTTPS `/login`, `/healthz`, CSS a JavaScript vrátili HTTP 200.
- V prehliadači bol úspešne odoslaný päťkrokový formulár a zobrazené potvrdenie uloženia.
- V PostgreSQL bol uložený fiktívny dopyt „TEST Overenie nasadenia“. Worker dokončil úlohu `analyze`; bez voliteľného súhlasu s AI bol stav `skipped`.
- V produkčnom kontajneri sa z tohto dopytu vygenerovalo platné PDF s veľkosťou 47 759 bajtov.
- Notifikácia je očakávane `blocked`, pretože `EMAIL_BACKEND=disabled`. Nebol odoslaný skutočný e-mail ani vykonané živé OpenAI volanie.
- Používateľ vytvoril prihlasovací účet priamo v Railway konzole; heslo nie je súčasťou projektu ani overovacích záznamov.

Pri aktuálnej kontrole má dashboard používateľovho účtu 0 dopytov; historický test nie je tvrdením o obsahu tohto účtu. Kompletný postup uloženia návrhu a odoslania sumarizácie v produkcii sa zatiaľ nevykonal; tieto scenáre pokrývajú automatizované testy. Podľa potreby zostáva doplniť API/e-mailové údaje.

Primárny kontaktný e-mail je `info@kubekfinance.sk`, prevádzkovateľ Dávid Kubek, IČO `55012469` a DIČ `2121841821`. Kontakt obsahuje obe identifikačné čísla a klikateľný e-mail; adresa sa nezobrazuje ani nevyžaduje. Prihlásenie predvyplní `info@kubekfinance.sk`.

Aktuálne nasadenie používa [portal.kubekfinance.sk](https://portal.kubekfinance.sk), doména je overená a certifikát má v Railway stav `VALID`. Web aj worker úspešne nasadili commit `e1ed2eace65be3b8807d715f2bc0fc08a7757863`; všetky štyri služby sú online. `/login`, `/healthz` a `/static/brand.css` na novej doméne vracajú HTTP 200. Prihlásenie na pôvodnej Railway doméne aj hlavný web `www.kubekfinance.sk` zostávajú dostupné (HTTP 200).

Vizuálna kontrola na počítači aj pri mobilnej šírke overila tmavomodrý vzhľad s tyrkysovými a fialovými prvkami a vlastnou ikonou podľa `kubekfinance.sk`. Spoločná téma v `static/brand.css` sa používa na prihlásení, dashboarde, dotazníku aj kontakte. Existujúca prihlásená relácia otvorila dashboard a odkaz na klientsky formulár už smeruje na novú doménu. Formulár sa na nej načítal; pri tejto zmene vzhľadu/domény sa nový produkčný dotazník neodosielal.

Lokálny Docker build, úplný automatizovaný PostgreSQL/Redis integračný test ani odosielanie skutočných správ neprebehli. Cloudový Docker build, štart služieb a vizuálna kontrola prihlasovacej stránky i odoslania dotazníka prebehli cez Railway a Chrome.

## Fiktívny výpočtový príklad

Príjem 3 000 EUR, bežné výdavky 1 200 EUR, dva dlhy spolu 90 000 EUR a splátky 630 EUR. DTI 2,50; pomer splátok k príjmu 21 %; zostatok 1 170 EUR.

Modelové refinancovanie 90 000 EUR pri 3,6 % na 25 rokov má splátku 455,40 EUR. Pri nových pravidelných nákladoch 20 EUR mesačne je zostatok 1 324,60 EUR a jeho zlepšenie 154,60 EUR mesačne. Ide o vymyslenú ponuku, nie aktuálnu sadzbu konkrétnej banky ani preukázanú celkovú úsporu.
