# West End Lunch → RSS

Inofficiellt RSS-flöde för lunchmenyn på [West End Food Court, Arendal](https://west-end.se/).
Ett inlägg per dag, som dyker upp i flödet samma morgon.

## Så funkar det

1. GitHub Actions kör `scrape.py` vardagar kl. ~07:15 och ~10:30.
2. Skriptet läser sidan, delar upp den per dag och station och skriver till `docs/`:
   - `feed.xml`: RSS-flödet
   - `index.html`: veckans meny som mobilvänlig sida
   - `menu.json`: historik (45 dagar)
3. GitHub Pages publicerar `docs/`, och flödet blir åtkomligt på
   `https://<ditt-användarnamn>.github.io/<reponamn>/feed.xml`

## Sätt upp (ca 5 min)

1. Skapa ett **publikt** repo på GitHub, t.ex. `west-end-rss`, och ladda upp alla filer (inklusive mappen `.github`).
2. **Settings → Actions → General → Workflow permissions:** välj *Read and write permissions* och spara.
3. **Actions**-fliken → *Uppdatera lunchflöde* → **Run workflow**. Då skapas `docs/` första gången.
4. **Settings → Pages:** Source *Deploy from a branch*, branch `main`, mapp `/docs`. Spara.
5. Lägg in flödets URL i din RSS-läsare efter en minut eller två.

## Testa lokalt

```bash
pip install -r requirements.txt
python scrape.py --html tests/fixture.html --today 2026-09-23 --out /tmp/test
python scrape.py --out docs --all-week     # live, hela veckan direkt
```

## Om något går sönder

- Hittar skriptet inga dagar (t.ex. om sidan byter layout) avslutas det med fel och
  **lämnar det gamla flödet orört**. GitHub mejlar dig när en körning misslyckas.
- Dagrubriken måste ha formatet `Måndag 21/9`. Stationsrubriker känns igen som
  rubriktaggar eller korta rader i VERSALER.
- Du ändrar vilka stationer som hoppas över i inläggsrubriken med `TITLE_SKIP` i `scrape.py`.

Skriptet hämtar sidan högst två gånger per vardag.
