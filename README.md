# Crate — Deployment Guide

Same process as BeeTik: new GitHub repo, connect to Render, deploy.

## Files
- `app.py` — backend (metadata fetching, genre detection, bookmark storage in SQLite)
- `templates/index.html` — the Save + Library page
- `requirements.txt` / `Procfile` — same role as before

## Steps
1. Create a new GitHub repo (e.g. `crate` or `crate-app`) — separate from your
   video-downloader/BeeTik repo, since this is a different project.
2. Upload all files from this folder (drag the `templates` folder in directly,
   don't use the file-picker for it — same trick as before).
3. In Render: New + → Web Service → connect this new repo.
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn app:app`
6. Instance Type: Free
7. Deploy.

## How it works
- **Save tab:** paste a link, it fetches the title/thumbnail/uploader via
  yt-dlp's metadata-only mode (no video/audio is ever downloaded), guesses a
  genre from the caption/hashtags, and lets you rename it and confirm the
  genre before saving.
- **Library tab:** browse everything you've saved, filterable by genre pills
  across the top. Each card has a "Go to original" link (opens the real video
  on its platform) and a delete button.
- **Storage:** bookmarks live in a local SQLite file (`crate.db`) on the
  server. Same caveat as the subscriber list in BeeTik — Render's free tier
  wipes local files on redeploy/restart, so treat this as a working prototype
  for now. Once you're happy with it, migrating to a proper hosted database
  (Render offers free Postgres) makes the data durable — happy to set that up
  when you're ready.

## What's NOT built yet (ideas from our brainstorm, for later)
- Share-target support (share directly from TikTok's share sheet)
- Mood tags alongside genre
- Broken-link checking
- Shareable public playlists
- Queue/autoplay mode
