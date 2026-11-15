# Miko Anime Room: integration report

## Approach
Inspected the project first (standard-library server `miko_server.py`, Stitch HTML screens in one iframe shell, `bridge.js` wiring, `MikoPlayer`
with its `resolve` option, `miko_downloads` job queue, `miko_chat` / `miko_voice` command + action path). Nothing was rebuilt. The Anime Room is a
new backend module + new screen + new script, plugged into the existing player, download manager, chat, voice and shell.
Every modified file was backed up to `backups/before_anime_room_20261114/`.

## Added / changed
Added: `miko_anime.py`, `ui/screens/anime-room.html`, `ui/assets/anime-room.js`, `ANIME_ROOM_README.txt`, this report.
Changed (additive): `miko_server.py` (screen, 20 `anime/*` endpoints, `/animeproxy/` relay), `miko_chat.py` (anime commands run before the generic
"search for"), `miko_voice.py` (opens the window on #anime-room), `ui/index.html` (route + command hand-off), `ui/assets/bridge.js` (Anime tab on all
screens), `ui/assets/miko-player.js` (optional `attach`/`detach` hooks, only used by the Anime Room), `install_extra_packages.bat` (+beautifulsoup4 lxml).
Byte-identical to your upload: all other files (Video Vault screen, downloads, search, research, settings, avatar, voice engine core, models ...).

## Requirements -> how
| You asked | Done by |
|---|---|
| Add and save any anime site URLs | My sites tab, `miko_anime.json`, per-site enable / search address / cookie, test button |
| Browse and search them inside Miko | Reader mode: pages fetched server-side and shown as cards (works for sites that refuse framing); back, next page, Live view when allowed |
| Watch inside Miko | Episode page -> stream finder -> local relay -> the existing Miko player (MP4 direct, HLS via hls.js, downloaded files from disk) |
| Download episode / range | Click, tick, or type `1-12`, `3,5,8-10`, `latest`; queued into Miko's download manager (2 at a time), shown in Downloads |
| Search by name | AniList names/posters + every selected site's own search (auto-detected form, common patterns, or your template) |
| Manage sites, downloads, library | Sites / Downloads / Library tabs (progress, watched, downloaded, continue, refresh, remove) |
| AI, voice, player, download manager | Chat/voice commands, confirm-before-download, side-panel AI knows what you are watching, "Ask Miko", same player, same job queue + history |

## Tests (Linux sandbox, real Miko server, real Chromium, a fake anime website I wrote)
| Suite | Result |
|---|---|
| Backend: site validation, SSRF guards, search-form discovery, lazy-image cards, nav/footer noise filtering, series/episode detection, title cleanup, 4 stream layouts (video tag, iframe->HLS, script JSON HLS, data-video embed), Cloudflare message, URL-template builder, range parser, 20 command phrasings incl. "no hijack" cases | 54 / 54 |
| API end-to-end: add/test/search/page, poster relay, Referer-protected MP4 with Range (206), HLS playlist rewrite + segment relay, bad token/Host/Origin refused, Miko-itself / link-local / file:// refused, range download of 3 episodes (direct + HLS) into Downloads\Miko\Anime\<series>, files verified with ffprobe, history + Videos "Downloaded" list + `/media` Range, skip-if-exists, watched/progress, library refresh, cancel queued jobs, chat command -> action -> queue, ordinary search untouched, existing APIs alive | 48 / 48 |
| Browser UI: screen loads, player mounted, Anime tab active/injected into other screens, add+test site from UI, search, open series (12 eps), range select + download (3 done), play via relay (video time advances), play from disk, library, browse cards, paste episode link -> build list, typed command "download episodes 6 to 8 of frieren anime" -> confirmation -> "confirm download", "watch frieren episode 2", "open the anime room" from the Videos screen, Video Vault still loads with its player, all other screens open | 25 / 25 (+1 expected: `tailwind is not defined`, the sandbox is offline; same on every existing screen) |
| yt-dlp path (stand-in executable): headers, progress parsing, concurrency flags | pass |

## NOT tested (honest limits)
- **Real anime websites.** The sandbox has no internet. Page parsing is heuristic; real sites vary and some will need a manual search address, the cookie field, or "Build list".
- **AniList** live calls (code written, offline here; if unreachable, search silently uses just your typed name).
- **hls.js playback in a browser**: hls.js loads from cdnjs at runtime (or `ui/assets/hls.min.js`); offline here, so only the relay playlist/segments and the hook wiring were verified, not hls.js decoding.
- **Real yt-dlp** (stand-in used), Windows 11 / Edge, microphone voice, Ollama replies, pixel-exact Stitch look (Tailwind was blocked).
- Cloudflare / captcha / JavaScript-only sites: reported with a clear message, not bypassed.
- Pause/resume for anime downloads (cancel works; pause is not offered).

## Security notes
Relay only serves URLs Miko itself found, behind unguessable tokens, and only to requests from Miko's own page (Host/Origin checks unchanged);
fetching refuses Miko's own port, loopback and private-network addresses unless you saved that exact host:port; redirects are re-checked every hop;
cookies you paste are stored in `miko_anime.json` on your PC and never sent to the page.
