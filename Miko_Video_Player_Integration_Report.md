# Miko Stitch + MikoGo video player: integration report

## 1. Inspection findings
**Miko Stitch (main project, kept as the foundation)**: Python standard-library HTTP server (`miko_server.py`, 127.0.0.1:8765) serving Stitch HTML screens in one iframe shell (`ui/index.html`). `ui/assets/bridge.js` is injected into each screen and wires the buttons to the Python API (`miko_search`, `miko_downloads`, `miko_research`, `miko_chat`, `miko_voice`). The Video Vault searched (ddgs) and could download, but had **no player**; it only opened links in the browser.

**MikoGo**: a Go file server with a browser front-end. The reusable part is one file, `public/libs/mediaViewer.js`: `SliderBar` (l.250), `MediaPlayer` (l.295: playlist, order modes, shortcuts), `VideoPlayer` (l.661: auto-hiding controls, fullscreen). The rest (Go server, file manager, pdf.js, highlight.js, PHP/Node legacy) was not copied.

**Licence**: MikoGo is MIT (c) 2021 MzeroMiko. Free to reuse; licence text is kept in `THIRD_PARTY_LICENSES/MikoGo-MIT.txt`.

**Compatibility problems found, and how they were handled**
| Problem in MikoGo code | Handling |
|---|---|
| Plays only `<audio>`/`<video>` files from its own server; no YouTube/embeds | New embed layer + link classifier |
| Slider uses `offsetLeft` (wrong position inside nested layouts), no drag | Rebuilt with pointer events + `getBoundingClientRect` |
| Global functions, inline-styled icons, uses implicit global `event` | Single namespaced `MikoPlayer`, scoped CSS, inline SVG icons (no icon-font/internet dependency) |
| `timeupdate` repaint on every event | UI refresh capped at about 2 Hz, none while the window is hidden |
| Miko's server returned whole files with `f.read()` and had no Range support | New `/media` endpoint with Range, only inside the Miko downloads folder |
| Screen frame could not go fullscreen | `allowfullscreen`/`allow` added to the shell iframe |
| yt-dlp downloads may be `.mkv`, which browsers often cannot play | Library flags them; fallback card offers "Open with Windows player" |

## 2. Files
**Added**: `miko_player.py` (backend: safe media streaming with Range, download library, optional yt-dlp stream resolver), `ui/assets/miko-player.js` (the player), `THIRD_PARTY_LICENSES/` (2 files), `VIDEO_PLAYER_README.txt`, `backups/before_video_player_20261114/` (originals of the 5 modified files).
**Modified (5)**: `miko_server.py` (+1 import, 2 API endpoints `video/library`, `video/resolve`, `/media` route, HEAD support: ~25 lines), `ui/assets/bridge.js` (Video Vault block only: player creation + hooks; other screens untouched), `ui/screens/video-vault.html` (player card + script tag), `ui/index.html` (fullscreen/autoplay permissions on the frame), `README_START_HERE.txt` (note appended).
**Verified unchanged** (byte-identical to your upload): all other Python files (chat/AI brain, voice, avatar, search, downloads, research), all other screens, settings, models, bat files.
Full original: `Miko_Stitch_ORIGINAL_BACKUP.zip`.

## 3. What was built
Embedded player in the Video Vault with play/pause, seek (click + drag), volume/mute, fullscreen, previous/next, ±10 s, play order (sequence / repeat all / repeat one / shuffle), keyboard shortcuts, picture-in-picture, a clickable playlist ("Up next" = search results) and a "Downloaded" playlist of the user's own downloads.
Source handling: YouTube (nocookie embed, two-way control via the IFrame message protocol, auto-next, embed-blocked detection) | direct MP4/WebM/OGV | local files via Range | Vimeo/Dailymotion/Bilibili/Twitch (view-only embeds) | any other page: optional yt-dlp stream, else a fallback card.

## 4. Testing report
Environment: Linux sandbox, real browser (Chrome for Testing 153, same Chromium engine as Edge) driving the **real Miko server**; fake search data (no internet / no ddgs in the sandbox); local Range-capable media server; ffmpeg-generated clips.
**76 automated browser checks, 76 passed**, plus 24 link-classification unit tests (passed), plus resolver tests.

| Area | Result |
|---|---|
| Application startup (server + shell + all 7 screens, zero JS errors) | Pass (also verified from a fresh unzip of the deliverable) |
| Direct MP4 over HTTP (VP9-in-MP4) | Pass |
| Local H.264 MP4, local AV1 MP4, local WebM, direct WebM (via /media with Range) | Pass |
| Seek by click and by drag, also on local files (Range) | Pass |
| Volume slider, mute/unmute | Pass |
| Play/pause button, Space, ±10 s, M, F | Pass |
| Fullscreen: button, double-click, F key, exit; YouTube iframe fullscreen | Pass |
| Playlist: select from results, Next, Previous history, wrap-around, auto-advance at video end (native and YouTube), order modes, Downloaded tab | Pass |
| Video selection from search results (cue on search, play on click, card highlight sync) | Pass |
| YouTube embed URL (nocookie, id, start time, origin, jsapi, allow/referrer) | Pass |
| YouTube control link (pause/seek/volume/duration/auto-next, error 150 fallback) | Pass **against a mock** of YouTube's documented message protocol |
| Fallback cards: blocked YouTube, unknown site, broken link, unsupported container (AVI) | Pass |
| yt-dlp resolver (stand-in executable): success, split streams, failure, non-http links | Pass; success path also played end-to-end |
| Security: path traversal, foreign Host header, non-media extensions | Blocked (404/403) |
| Idle cost: time display refreshes about 2x/s while playing; nothing runs while idle | Pass |
| Existing: web, image, news, video search APIs; file download start/complete; downloads list/usage; research, memory, config, status, voice-events endpoints | Pass |

**Not tested here (honest limits)**
- **Live YouTube** (sandbox has no internet): the iframe protocol was tested against a mock, not youtube.com. If YouTube rejects embeds from `http://127.0.0.1` for some video, the player shows the fallback card rather than a blank frame.
- Vimeo / Dailymotion / Bilibili / Twitch: URL builders unit-tested only; never loaded. Twitch may refuse `127.0.0.1` as a parent domain.
- Real Edge on Windows 11 and your GPU. Edge uses the same Chromium engine; hardware decoding is automatic but CPU/GPU load was not measured on your PC.
- Voice recognition, microphone, Ollama chat, avatar, wallpaper: need Windows hardware/services. Their files are unchanged (byte-identical) and not touched by the player. Search was tested with stubbed back-ends; the Tavily/ddgs live calls need your internet.
- The Stitch look needs Tailwind/fonts from the internet (as before); tests stubbed them, so pixel-exact appearance inside the full Stitch layout was checked only for the player component (at 480 px and 360 px wide), not in the final composite.

## 5. Remaining limitations / unsupported sites
- DRM/subscription: Netflix, Disney+, Prime Video, Hulu, Crunchyroll, etc. cannot be embedded (cannot be fixed). Also TikTok, Instagram, Facebook and most anime-streaming pages block embedding; the card offers browser / small window / yt-dlp stream / download.
- YouTube videos whose owners disable embedding (errors 101/150/153) -> fallback card.
- HLS (.m3u8) is not played natively (hls.js was left out to keep it dependency-free); MKV/AVI/WMV depend on Edge's codecs.
- Embeds other than YouTube cannot be controlled by Miko's buttons and do not auto-advance.
- Behaviour changes: double-click on a card now fullscreens the player (it used to open the browser); "Float PiP" uses real PiP for native video.

## 6. Dependencies
None new. Already installed by `install_extra_packages.bat`: `requests ddgs ollama yt-dlp numpy pillow edge-tts sounddevice pygame faster-whisper`. Optional: `winget install Gyan.FFmpeg` (merge HD downloads), `pip install -U yt-dlp`.

## 7. Windows 11 installation
1. Unzip `Miko_Stitch_with_VideoPlayer.zip` (e.g. `D:\Miko_Stitch`); your original is untouched.
2. First time: run `install_extra_packages.bat` (nothing new is required).
3. Start Ollama, then run `start_miko_stitch_debug.bat` (or `start_miko_stitch.bat`).
4. Videos tab -> search -> click a result.
Rollback: copy files from `backups\before_video_player_20261114\` back, delete `miko_player.py` and `ui\assets\miko-player.js`.
