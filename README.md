# Subtitle Checker v0.1.0

**Syfte:** Kontrollera om svenska och engelska undertexter verkar finnas till filmer som är registrerade i Radarr **innan videofilen laddas ned**. Läsbart webbgränssnitt, lokal SQLite-cache, Docker på ThinkPad.

- Radarr v3 (API-nyckeln används endast till `GET /api/v3/movie`).
- OpenSubtitles.com REST-API (två sökningar per film, en för `sv` och en för `en`).
- IMDb-ID används i första hand. Om det saknas söks titel + år (resultaten måste kontrolleras extra noga).
- Antal undertextträffar och upp till fem exempel/releasenamn per språk.
- Visar enbart filmer utan fil (`hasFile=false`) och oavsett `monitored`.
- Sparar träffarna i SQLite och hoppar normalt över sökningar yngre än `CACHE_HOURS`.
- Exponerar inte API-nycklar i webb-API:et. Inga undertexter eller filmer laddas ned.
- Ingen koppling till SRT Translator än (planerat för senare steg).

## Förberedelser

Du behöver **två API-nycklar**:

1. **Radarr:** Settings → General → Security → API Key.
2. **OpenSubtitles.com:** skapa konto och en *API Consumer* på <https://www.opensubtitles.com/en/consumers>. Kopiera API-nyckeln. En API-nyckel räcker för att **söka**. Webbappen laddar inte ned SRT-filer.

Sökarbetet behöver ingen videofil och ingen Plex-anslutning.

## Installation på ThinkPad

```bash
mkdir -p ~/Production
cd ~/Production
git clone https://github.com/unilsson/subtitle-checker.git
cd subtitle-checker
cp .env.example .env
nano .env                 # Fyll i API-nycklarna och välj hostport
chmod 600 .env
mkdir -p data
sudo chown 10001:10001 data
# För vissa rootless Docker-installationer kan du behöva andra filrättigheter.
docker compose up -d --build
docker compose ps
# Visa vald hostport
docker compose port subtitle-checker 8097
docker compose logs --tail=50
```

**Lösenord och API-nycklar ska aldrig commitas i Git.** `.env` är gitignorerad och ska endast finnas på din server. För Radarr som kör i Docker på samma värd kan du ange `RADARR_URL=http://192.168.1.14:7878` om porten är publicerad på ThinkPad. `localhost` inuti en container pekar inte på värddatorn.

Öppna `http://192.168.1.14:8097` från hemnätet **om du behåller standardporten**.

### Byt hostport om 8097 redan används

Ändra följande i `.env`, exempelvis:

```dotenv
SUBTITLE_CHECKER_PORT=8105
SUBTITLE_CHECKER_BIND=0.0.0.0
```

Kör därefter `docker compose up -d --force-recreate`. Webbsidan nås då på
**`http://192.168.1.14:8105`**. Du kan välja vilken ledig port som helst
(i normalfallet 1024–65535). **Det är bara Docker-värdens port som ändras;
appen och healthcheck kör alltid på port 8097 inuti containern.**

För att enbart tillåta åtkomst från ThinkPad kan du ange
`SUBTITLE_CHECKER_BIND=127.0.0.1` (webbsidan är då inte direkt åtkomlig från Elite).
Välj inte en port som används av dina andra Docker-tjänster. Kolla exempelvis
med `docker ps --format 'table {{.Names}}\\t{{.Ports}}'` och `sudo ss -ltnp`.
Om du ändrar porten senare behöver du återskapa containern, men din SQLite-databas
ligger kvar i `./data`.

### Kom igång

1. Klicka **Synka filmer från Radarr** – hämtar filmtitlar utan externa sökningar.
2. Klicka **Kontrollera undertexter** – söker svenska och engelska på OpenSubtitles.
3. Filtrera på **Svenska finns**, **Endast engelska**, **Inga träffar** osv.
4. Klicka **Detaljer** för att se exempel på releaser och deras OpenSubtitles-länkar.
5. **Kontrollera om alla** gör om sökningarna även om cache finns.

### Inställningar i `.env`

| Inställning | Standard | Funktion |
|---|---|---|
| `SUBTITLE_CHECKER_PORT` | `8097` | **Hostporten** för webbgränssnittet, t.ex. `8105` |
| `SUBTITLE_CHECKER_BIND` | `0.0.0.0` | Vilken nätverksadress på ThinkPad som hostporten binds till |
| `RADARR_URL` | `http://radarr:7878` | Radarr som containern kan nå |
| `RADARR_API_KEY` | – | Radarr-nyckel |
| `OPENSUBTITLES_API_KEY` | – | OpenSubtitles Consumer-nyckel |
| `CACHE_HOURS` | `24` | Sökträffar yngre än detta återanvänds |
| `REQUEST_DELAY_MS` | `500` | Minst 250 ms mellan sökningar |
| `MAX_SCAN_MOVIES` | `0` | 0 = alla saknade, annat = max per körning |
| `AUTO_SCAN_HOURS` | `0` | 0 = endast manuell; annat = schemalagd synk och kontroll |

Ändrad `.env` kräver `docker compose up -d --force-recreate`. Ingen databasförstöring vid normal uppdatering.

## Begränsningar

- **Finns undertext?** betyder att OpenSubtitles har träffar för filmen. En senare filmnedladdning kan ha andra tidskoder. Det är ingen garanti för synk.
- **Inga träffar** betyder inga träffar i den utförda sökningen, inte att undertexter aldrig existerar. Providerfel markeras separat.
- Filmer utan IMDb-ID söks med titel och år. Det är osäkrare.
- Flera undertexter kan vara hearing-impaired eller maskinöversatta; dessa markeras i detaljvyn.
- Bara **första sidan av sökresultat** och fem exempel visas per språk. Om OpenSubtitles rapporterar `total_count` visas den totalsiffran.
- **Inga automatiska nedladdningar** och **ingen möjlighet att välja korrekt release i Radarr** i denna version.
- Dashboarden har **ingen inbyggd inloggning**. Exponera därför **inte den valda hostporten på internet**. Använd bara på betrott LAN/VPN, helst begränsat via OPNsense-brandväggen.
- Varje film kräver två sökningar. Kontrollera OpenSubtitles kvoter och nyttja cachen innan du aktiverar schemalagd massökning.

## Diagnostik

```bash
cd ~/Production/subtitle-checker
docker compose ps
docker compose logs --tail=100
# Ersätt 8097 med SUBTITLE_CHECKER_PORT om du valde en annan port.
curl -s http://192.168.1.14:8097/health
curl -s http://192.168.1.14:8097/api/status | python3 -m json.tool
```

## API

| Metod | Endpoint | Funktion |
|---|---|---|
| `GET` | `/health` | Hälsa |
| `GET` | `/api/status` | Konfiguration utan hemligheter, jobbsteg, sammanfattning |
| `GET` | `/api/movies` | Lista inklusive sökresultat |
| `POST` | `/api/sync` | Radarr-synk (JSON-body + X-Requested-With) |
| `POST` | `/api/scan` | Sök, ev. `{ "movie_id": 123, "force": true }` |

## Lokal utveckling / tester

Ingen tredjeparts-Pythonkod krävs (bara standardbiblioteket):

```bash
python3 -m unittest discover -s tests -v
DB_PATH=/tmp/subtitle-checker-dev.sqlite3 PORT=8097 \\
 RADARR_URL=http://localhost:7878 \\
 RADARR_API_KEY=... OPENSUBTITLES_API_KEY=... python3 -m app.server
```

## Källor och API-dokumentation

- <https://radarr.video/docs/api/>
- <https://opensubtitles.tawk.help/article/getting-started>
- <https://blog.opensubtitles.com/opensubtitles/how-to-build-a-movie-subtitle-finder-cli-with-python-and-the-opensubtitles-api>

Detta är en fristående privat tjänst och varken en officiell Radarr- eller OpenSubtitles-produkt.
