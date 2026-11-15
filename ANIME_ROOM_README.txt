MIKO ANIME ROOM
===============

OPEN IT
Click the new "Anime" tab at the top of any Miko screen (between Videos and Downloads).

INSTALL (Windows 11)
1. Unzip this project anywhere (your old folder is untouched if you unzip next to it).
2. Double-click install_extra_packages.bat once. It now also installs beautifulsoup4 and lxml (needed to read websites).
   yt-dlp is already in that list. ffmpeg is optional but recommended:  winget install Gyan.FFmpeg
3. Start Ollama as usual, then start_miko_stitch_debug.bat (or start_miko_stitch.bat).

FIRST USE
1. Anime tab > "My sites" > paste the address of an anime website you use > Save site. Miko tests it and tries to find its search box.
   You can save as many sites as you like; tick "Use in search" per site. Miko ships with NO site list.
2. Type an anime name in the big box and press Enter. Miko asks AniList for the proper names (so "AOT" finds "Shingeki no Kyojin" too)
   and searches every selected site. Click a result.
3. The series page lists the episodes. Click the play button to watch inside Miko (right side, the same player as the Videos tab).
   Tick episodes, or type a range like  1-12  or  3,5,8-10  or  latest  and press Select, then "Download selected".
4. Downloads go through Miko's normal download manager (two at a time, shown in the Downloads screen too) into
   Downloads\Miko\Anime\<series name>\ . Finished episodes appear in the player's "Downloaded" tab and play from disk.

OTHER THINGS YOU CAN DO
- Paste any page link in the search box to browse it as cards ("Browse" tab). Back, next page, "Open in my browser", and "Live view"
  (shows the real page when the site allows it) are there too.
- Paste ONE episode link and press "Build list": Miko guesses the other episode links (Episode 1..N) from the pattern. Handy when a site
  fills its episode list with scripts.
- Library tab: your series, watched count, downloaded count, "Continue E5", refresh (look for new episodes), remove.
  Watching more than 90% of an episode marks it watched; Miko resumes where you stopped.
- Sites tab > Advanced: set a search address by hand (use {q} for the name, e.g. https://site.com/?s={q}), or paste a browser Cookie
  header for sites that need your login or an anti-bot check.

TALK TO MIKO (typed in the side panel, or spoken after "Miko")
  "open the anime room"                         "continue watching anime"
  "find anime Frieren"                          "watch Frieren episode 5"  /  "play one piece episode twelve"
  "download episodes 1 to 12 of One Piece"      "download the latest episode of Frieren"  /  "download all episodes of Naruto"
  "add anime site https://example.com"          "confirm download"
Downloads by voice or chat are never started blindly: Miko opens the series, selects the episodes and asks you to press Download
(or say "confirm download"). Ordinary requests like "search for pasta" or "play some music" are not touched.
"Ask Miko" on a series page asks your local AI for a short spoiler-free summary; the side-panel chat also knows what you are watching.

HOW STREAMS ARE FOUND
Miko opens the episode page, looks for video tags, .mp4/.m3u8 links and embedded players (it follows them), checks the link really
answers like a video, then plays it through a small local relay on this PC that adds the Referer the site expects. If that fails it asks
yt-dlp. The player's "Try direct stream" button cycles to the next source found. HLS (.m3u8) playback uses hls.js:
Miko loads it from the internet the first time; to work fully offline put hls.min.js in ui\assets\ .
HLS downloads: Miko's own downloader (fast, 4 parts at once) makes an .mp4 if ffmpeg is installed, otherwise a .ts file;
encrypted/unusual streams fall back to yt-dlp, then ffmpeg.

LIMITS (please read)
- Sites that hide everything behind scripts, logins, captchas or Cloudflare challenges may show nothing. Use "Open in my browser", the
  cookie field, "Build list", or yt-dlp-supported sites. DRM services (Netflix, Crunchyroll, Disney+ ...) cannot be played or downloaded.
- Every site is different; the reader finds cards/episodes by common patterns, not by site-specific rules. Tell me which sites misbehave and a
  rule can be added.
- Only use sites and content you are allowed to access where you live. Miko just reads pages and downloads what you ask for.
- Addresses inside your own network (192.168.x.x, localhost) are blocked unless you saved that exact address as a site.

FILES ADDED:   miko_anime.py   ui\screens\anime-room.html   ui\assets\anime-room.js   ANIME_ROOM_README.txt   ANIME_ROOM_REPORT.md
FILES CHANGED (additive; originals in backups\before_anime_room_20261114\):
  miko_server.py (screen + 20 anime/* endpoints + /animeproxy relay), miko_chat.py (anime commands before the generic search),
  miko_voice.py (opens the Anime Room window when you speak a command and no window is open), ui\index.html (route + command hand-off),
  ui\assets\bridge.js (Anime tab on every screen), ui\assets\miko-player.js (two optional hooks used for HLS; nothing changes without them),
  install_extra_packages.bat (+beautifulsoup4 lxml), README_START_HERE.txt (note).
Your data: miko_anime.json (sites, library, progress) in this folder. Delete it to start the Anime Room from scratch.

UNDO: copy the files from backups\before_anime_room_20261114\ back over the originals and delete the files listed under "FILES ADDED".
