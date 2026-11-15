MIKO STITCH  (working copy - your original Miko files are untouched in this folder)

FIRST TIME
1. Double-click  install_extra_packages.bat   (one time; skips what you already have)
2. Make sure Ollama is running (same as you use for Miko today).
3. Double-click  start_miko_stitch_debug.bat   -> Miko opens in its own window.
   If something is wrong you can read the message in the black window.
4. Once it works, use  start_miko_stitch.bat  (no black window).

IMPORTANT
- Use EITHER the new Miko Stitch OR the old start_miko.bat, not both at once (they would fight over the microphone).
- Voice is OFF until you switch on "Hands-free voice" in Settings. Then say "Miko".
- The old Miko still works: start_miko.bat is unchanged.
- Settings > "Connections & About" shows which Python packages are missing.

NEEDS INTERNET FOR: the look (fonts/icons load online), web/image/video/news search, downloads, and Miko's voice (Microsoft edge-tts, free).
Ollama and the speech recognition (faster-whisper) run on your PC.
Videos/MP3 downloads need yt-dlp (installed by install_extra_packages.bat).


VIDEO PLAYER (added)
- Open the Videos tab, search, and click a result: it plays inside Miko. See VIDEO_PLAYER_README.txt.
- No new packages are needed. The original files of this change are saved in backups\before_video_player_20261114\


ANIME ROOM (added)
- New "Anime" tab: save your own anime sites, search by name, watch in Miko, download episodes or ranges. See ANIME_ROOM_README.txt.
- Run install_extra_packages.bat once more (adds beautifulsoup4 + lxml).
- Originals of every changed file: backups\before_anime_room_20261114\
