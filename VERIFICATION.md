# Overenie opravenej verzie

Dátum: 18. 10. 2026. Prostredie: Windows, Python 3.12.14, samostatné virtuálne prostredie.

| Kontrola | Výsledok |
|---|---|
| `python -m pytest -q` | Všetkých 42 testov úspešných |
| Neplatný alebo chýbajúci `ENCRYPTION_KEY` | 4 regresné prípady; zrozumiteľná chyba bez vypísania hodnoty kľúča |
| Platná produkčná konfigurácia | HTTPS prihlasovacia stránka, bezpečnostné hlavičky a `/healthz` po vytvorení schémy úspešné |
| Výpočty | 15 testov vrátane nulového príjmu/úroku, refinancovania a validácie vstupov |
| Webové routy | 11 testov vrátane skutočného CSRF tokenu, oddelenia agentov a nemenných sumarizácií |
| Worker, AI, PDF a e-mailové adaptéry | 11 testov; OpenAI a prenos SMTP/SendGrid simulované |

Testy používajú dočasnú SQLite databázu. Produkčný PostgreSQL, Redis a správanie Railway tým nie sú overené. Validácia šifrovacieho kľúča pôvodnú hodnotu nemení ani automaticky negeneruje novú.

## Stav nasadenia

Pri kontrole existujúceho nasadenia bol zistený neplatný `ENCRYPTION_KEY` a neúplný obsah GitHub repozitára bez priečinkov so šablónami, statickými súbormi a fontmi. Opravený zdroj obsahuje tieto súbory a návod používa nastavenia Railway dashboardu.

**Overenie opraveného živého nasadenia zatiaľ čaká.** Úspešné lokálne testy neznamenajú úspešné nasadenie. Po nasadení treba overiť web, bežiaci worker, uloženie fiktívneho dotazníka, dokončenie analýzy a otvorenie PDF. Živé OpenAI volanie a skutočný e-mail sa overia až po doplnení príslušných prihlasovacích údajov.

V tomto overení neprebehol Docker build, Gunicorn v linuxovom kontajneri, PostgreSQL/Redis integračný beh, vizuálna kontrola v prehliadači ani odosielanie skutočných správ. Predchádzajúce tvrdenia o týchto kontrolách sa nepovažujú za nové overenie opravenej verzie.

## Fiktívny výpočtový príklad

Príjem 3 000 EUR, bežné výdavky 1 200 EUR, dva dlhy spolu 90 000 EUR a splátky 630 EUR. DTI 2,50; pomer splátok k príjmu 21 %; zostatok 1 170 EUR.

Modelové refinancovanie 90 000 EUR pri 3,6 % na 25 rokov má splátku 455,40 EUR. Pri nových pravidelných nákladoch 20 EUR mesačne je zostatok 1 324,60 EUR a jeho zlepšenie 154,60 EUR mesačne. Ide o vymyslenú ponuku, nie aktuálnu sadzbu konkrétnej banky ani preukázanú celkovú úsporu.
