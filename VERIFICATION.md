# Overenie dodanej verzie

Dátum: 18. 10. 2026. Prostredie: Python 3.12.14, Linux.

| Kontrola | Výsledok |
|---|---|
| `python -m pytest` | 37 úspešných testov |
| Inicializácia `.env` a databázy podľa návodu | Úspešná |
| Vytvorenie účtu cez CLI, reset hesla a odhlásenie starých relácií zmenou verzie | CLI a nové prihlásenie úspešné; mechanizmus verzie relácie implementovaný |
| Prihlásenie s reálnym CSRF tokenom a načítanie dashboardu | Úspešné |
| Gunicorn s dvoma workermi, HTTP `/healthz`, HTTP `/login`, bezpečnostné hlavičky | Úspešné; použitý `--no-control-socket` |
| `python worker.py --once` na prázdnej fronte | Úspešné |
| `node --check static/app.js` | Syntax v poriadku |
| `python -m pip check` | Bez konfliktov nainštalovaných balíkov |
| Vzorový PDF report | 2 strany; textová aj vizuálna kontrola oboch strán, diakritiky, tabuliek a hlavičiek |
| OpenAI | Skutočný SDK a štruktúrované parsovanie, HTTP odpoveď simulovaná |
| SMTP / SendGrid | Správa, PDF príloha a kópia agentovi overené so simulovaným prenosom |

Pri reálnom prihlasovacom teste sa opravila konfigurácia životnosti CSRF tokenu na počet sekúnd a test bol rozšírený o platný token a úspešné prihlásenie. PDF má kontrolované stránkovanie so samostatnou stranou návrhu a vlastným záhlavím na každej strane.

## Čo sa v tomto prostredí nevykonalo

- Volanie živého OpenAI API a odoslanie skutočného e-mailu: neboli dodané prihlasovacie údaje, správy sa neposielali.
- Prehliadačová kontrola vzhľadu a ovládania na mobile/desktope: vykonali sa serverové testy stránok a kontrola syntaxe JS, nie ovládanie v reálnom prehliadači.
- Docker build, PostgreSQL/Redis integračný beh a nasadenie Railway/Render: Docker tu nie je dostupný. Databázové testy prebehli na SQLite; cloudové nastavenia sú pripravené podľa dokumentácie a vyžadujú overenie pri nasadení.
- Penetračný test, záťažový test, právne posúdenie spracúvania a odborné bankové schválenie.

## Fiktívny výpočtový príklad z PDF

Príjem 3 000 EUR, bežné výdavky 1 200 EUR, dva dlhy spolu 90 000 EUR a splátky 630 EUR. DTI 2,50; pomer splátok k príjmu 21 %; zostatok 1 170 EUR.

Modelové refinancovanie 90 000 EUR pri 3,6 % na 25 rokov má splátku 455,40 EUR. Pri nových pravidelných nákladoch 20 EUR mesačne je zostatok 1 324,60 EUR a jeho zlepšenie 154,60 EUR mesačne. Ide o vymyslenú ponuku, nie aktuálnu sadzbu konkrétnej banky ani preukázanú celkovú úsporu.
