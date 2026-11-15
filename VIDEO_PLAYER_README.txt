MIKO VIDEO PLAYER  (integrated from MikoGo's player design, MIT)
================================================================

WHAT YOU GET
- Videos tab > click any result > it plays in the panel on the right (first result is only "cued": nothing loads
  until you press play, so Miko stays light).
- YouTube links play in an embedded player (youtube-nocookie.com) that Miko can control: play/pause, seek, volume,
  fullscreen, and it moves to the next video by itself when one ends.
- Direct .mp4 / .webm / .ogv / .m4v links play natively (hardware decoded by Edge/Chrome).
- Vimeo / Dailymotion / Bilibili / Twitch VOD links open in their own embedded player (view-only: their controls).
- "Downloaded" tab = every video/audio you downloaded with Miko (Downloads folder) - plays straight from disk,
  seeking works.
- Playlist: "Up next" = the current search results. Previous / Next, play order (in sequence, repeat all,
  repeat one, shuffle).
- If a site refuses to be embedded you get a clear card with: Open in my browser, Open in small window, Try direct
  stream (needs yt-dlp), Download it, Next video.

CONTROLS
 Space / K  play-pause        Left / Right  -10 s / +10 s       Up / Down  volume
 M  mute                      F or double-click  fullscreen     N / P  next / previous
 (click the player once first so it has keyboard focus)
 Button row: previous, back 10 s, play, forward 10 s, next, mute + volume, play order, picture-in-picture,
 open original page, fullscreen.

THINGS THAT BEHAVE DIFFERENTLY FROM BEFORE
- Double-clicking a result card used to open it in your browser. Now it makes the player fullscreen.
  "Open in my browser" is a button in the player (and on the fallback card).
- "Float PiP" now uses real Picture-in-Picture when a native (MP4/WebM/downloaded) video is playing.
  For YouTube/other embeds it still opens the small pop-up window like before.

WINDOWS 11 INSTALLATION
1. Unzip Miko_Stitch_with_VideoPlayer.zip anywhere (e.g. D:\Miko_Stitch). Your old Miko_Stitch folder is untouched
   if you unzip next to it.
2. First time only: double-click install_extra_packages.bat (same as before; no new packages are required).
3. Start Ollama as usual, then double-click start_miko_stitch_debug.bat (or start_miko_stitch.bat).
4. Open the Videos tab, search, click a video.
Optional (free):
   pip install -U yt-dlp          (already installed by install_extra_packages.bat; enables "Try direct stream"
                                   and video downloads)
   winget install Gyan.FFmpeg     (lets yt-dlp merge HD video+audio; recommended if downloads come out as .mkv)

LIGHT ON CPU/GPU
- No background timers or animation while idle; the time display updates twice a second and not at all while the
  window is hidden; no preloading of videos you did not click; the old source is released when you switch videos.
- Playback uses the browser's own hardware decoder (your RX 6600 XT handles H.264/VP9/AV1 in Edge).

UNDO
- Everything changed is saved in backups\before_video_player_20261114\ . To go back, copy those files over the
  originals (miko_server.py, ui\index.html, ui\assets\bridge.js, ui\screens\video-vault.html,
  README_START_HERE.txt) and delete miko_player.py and ui\assets\miko-player.js. The untouched original is also
  in Miko_Stitch_ORIGINAL_BACKUP.zip.

LIMITATIONS
- DRM / subscription services (Netflix, Disney+, Prime Video, Crunchyroll, Hulu...), TikTok, Instagram, Facebook
  and most anime streaming sites cannot be embedded. Miko shows the fallback card; yt-dlp may still find a
  stream for some non-DRM sites.
- Some YouTube videos forbid embedding (error 101/150/153) -> fallback card.
- HLS (.m3u8) and MKV/AVI/WMV files: depends on the codecs inside Edge; otherwise fallback card
  ("Open with Windows player" for files you downloaded).
- Needs internet for YouTube etc. and for the Stitch look (fonts/Tailwind load online - unchanged).
