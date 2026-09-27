import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Flask, render_template, request, jsonify, g
import yt_dlp

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "crate.db")

# Known genre keywords to match against a video's hashtags/caption. Add to
# this list freely — matching is case-insensitive substring matching.
GENRE_KEYWORDS = {
    "Afrobeats": ["afrobeats", "afrobeat"],
    "Amapiano": ["amapiano", "piano"],
    "Alte": ["alte"],
    "Highlife": ["highlife"],
    "Fuji": ["fuji"],
    "Juju": ["juju"],
    "Tungba": ["tungba"],
    "Gqom": ["gqom"],
    "Afro-house": ["afrohouse", "afro-house"],
    "Hip-Hop": ["hiphop", "hip-hop", "rap"],
    "R&B": ["rnb", "r&b"],
    "Pop": ["pop"],
    "Rock": ["rock"],
    "Jazz": ["jazz"],
    "Reggae": ["reggae"],
    "Dancehall": ["dancehall"],
    "Gospel": ["gospel", "worship"],
    "EDM": ["edm", "electronic"],
    "House": ["house"],
    "Drill": ["drill"],
    "Lo-fi": ["lofi", "lo-fi"],
    "Soul": ["soul"],
    "Funk": ["funk"],
    "Trap": ["trap"],
    "Soca": ["soca"],
    "K-pop": ["kpop", "k-pop"],
}

GENRE_LIST = list(GENRE_KEYWORDS.keys()) + ["Uncategorized"]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            platform TEXT,
            title TEXT,
            original_title TEXT,
            thumbnail TEXT,
            uploader TEXT,
            genre TEXT,
            notes TEXT,
            video_id TEXT,
            embed_url TEXT,
            duration REAL,
            created_at TEXT
        )
    """)
    # Add columns if upgrading an older db that predates embed support.
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(bookmarks)")}
    if "video_id" not in existing_cols:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN video_id TEXT")
    if "embed_url" not in existing_cols:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN embed_url TEXT")
    if "duration" not in existing_cols:
        conn.execute("ALTER TABLE bookmarks ADD COLUMN duration REAL")
    conn.commit()
    conn.close()


init_db()


def _detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "tiktok" in host:
        return "TikTok"
    if "instagram" in host:
        return "Instagram"
    if "youtube" in host or "youtu.be" in host:
        return "YouTube"
    return host or "Unknown"


def _build_embed_url(platform: str, video_id: str) -> str | None:
    """Official, platform-hosted embed URLs only — playback happens on the
    platform's own servers via their own permitted embed player. We never
    fetch or serve the underlying audio/video ourselves."""
    if not video_id:
        return None
    if platform == "TikTok":
        return f"https://www.tiktok.com/embed/v2/{video_id}"
    if platform == "YouTube":
        return f"https://www.youtube.com/embed/{video_id}"
    # Instagram's oEmbed now requires an authenticated app token to use,
    # so it's left out for now — those cards fall back to "Go to original".
    return None


def _suggest_genre(text: str) -> str:
    text = (text or "").lower()
    for genre, keywords in GENRE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return genre
    return "Uncategorized"


@app.route("/")
def index():
    return render_template("index.html", genres=GENRE_LIST)


@app.route("/api/preview", methods=["POST"])
def preview():
    data = request.get_json(force=True)
    url = (data or {}).get("url", "").strip()

    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"error": "Please provide a valid video URL."}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"error": f"Couldn't fetch that link: {str(e)[:200]}"}), 400

    title = info.get("title") or "Untitled"
    description = info.get("description") or ""
    thumbnail = info.get("thumbnail") or ""
    uploader = info.get("uploader") or info.get("channel") or ""
    video_id = info.get("id") or ""
    duration = info.get("duration")  # seconds, used as an autoplay-timer
    # fallback for platforms with no native "video ended" event (TikTok)
    suggested_genre = _suggest_genre(title + " " + description)
    platform = _detect_platform(url)
    embed_url = _build_embed_url(platform, video_id)

    return jsonify({
        "title": title,
        "thumbnail": thumbnail,
        "uploader": uploader,
        "platform": platform,
        "suggested_genre": suggested_genre,
        "original_url": url,
        "video_id": video_id,
        "embed_url": embed_url,
        "duration": duration,
    })


@app.route("/api/bookmarks", methods=["GET"])
def list_bookmarks():
    genre = request.args.get("genre")
    db = get_db()
    if genre and genre != "All":
        rows = db.execute(
            "SELECT * FROM bookmarks WHERE genre = ? ORDER BY created_at DESC", (genre,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM bookmarks ORDER BY created_at DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/bookmarks", methods=["POST"])
def save_bookmark():
    data = request.get_json(force=True)

    url = (data or {}).get("url", "").strip()
    title = (data or {}).get("title", "").strip()
    genre = (data or {}).get("genre", "Uncategorized").strip()
    notes = (data or {}).get("notes", "").strip()
    thumbnail = (data or {}).get("thumbnail", "").strip()
    uploader = (data or {}).get("uploader", "").strip()
    original_title = (data or {}).get("original_title", "").strip()
    video_id = (data or {}).get("video_id", "").strip()
    duration = (data or {}).get("duration")

    if not url:
        return jsonify({"error": "Missing URL."}), 400
    if not title:
        title = original_title or "Untitled"
    if not genre:
        genre = "Uncategorized"

    platform = _detect_platform(url)
    embed_url = _build_embed_url(platform, video_id)

    bookmark_id = uuid.uuid4().hex[:12]
    db = get_db()
    db.execute(
        """INSERT INTO bookmarks
           (id, url, platform, title, original_title, thumbnail, uploader, genre, notes, video_id, embed_url, duration, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            bookmark_id, url, platform, title, original_title,
            thumbnail, uploader, genre, notes, video_id, embed_url, duration,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    return jsonify({"ok": True, "id": bookmark_id})


@app.route("/api/bookmarks/<bookmark_id>", methods=["PATCH"])
def update_bookmark(bookmark_id):
    data = request.get_json(force=True)
    db = get_db()

    row = db.execute("SELECT * FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    title = (data or {}).get("title", row["title"])
    genre = (data or {}).get("genre", row["genre"]).strip() or row["genre"]
    notes = (data or {}).get("notes", row["notes"])

    db.execute(
        "UPDATE bookmarks SET title = ?, genre = ?, notes = ? WHERE id = ?",
        (title, genre, notes, bookmark_id),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/bookmarks/<bookmark_id>", methods=["DELETE"])
def delete_bookmark(bookmark_id):
    db = get_db()
    db.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/genres", methods=["GET"])
def get_genres():
    # Presets plus any custom genres the user has actually saved into —
    # so a typed-in genre shows up as a real filter/pill afterward, not
    # just accepted once and forgotten.
    db = get_db()
    used = {row[0] for row in db.execute("SELECT DISTINCT genre FROM bookmarks") if row[0]}
    preset = [g for g in GENRE_LIST if g != "Uncategorized"]
    custom = sorted(g for g in used if g not in GENRE_LIST)
    return jsonify(preset + custom + ["Uncategorized"])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

