"""
Construye el panel de lectura a partir de los feeds RSS de YouTube.

Lee data/suscripciones_categorizadas.csv (ID del canal, Título del canal, categoria),
descarga el feed RSS público de cada canal, agrupa los videos recientes por categoría,
y renderiza docs/index.html (una sola página estática, sin backend).

No requiere API key ni cuota: los feeds RSS de YouTube son públicos y no cuentan
contra ningún límite de la YouTube Data API.
"""
import csv
import json
import re
import time
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

import requests
import feedparser
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
DATA_CSV = ROOT / "data" / "suscripciones_categorizadas.csv"
STATE_FILE = ROOT / "data" / "last_seen.json"
OUTPUT_HTML = ROOT / "docs" / "index.html"
TEMPLATE_DIR = ROOT / "templates"

MAX_WORKERS = 20          # descargas concurrentes
TIMEOUT_SECONDS = 10      # por feed individual
VIDEOS_PER_CHANNEL = 6    # cuántos videos recientes conservar por canal
RETRIES = 2


def fetch_channel_feed(channel_id: str, title: str, category: str) -> list[dict]:
    """Descarga y parsea el feed RSS de un canal. Nunca lanza excepción hacia afuera:
    un canal caído o sin feed simplemente aporta una lista vacía."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    for attempt in range(RETRIES + 1):
        try:
            resp = requests.get(url, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            videos = []
            for entry in feed.entries[:VIDEOS_PER_CHANNEL]:
                pub_struct = entry.get("published_parsed")
                pub_dt = (
                    datetime(*pub_struct[:6], tzinfo=timezone.utc)
                    if pub_struct
                    else None
                )
                thumb = ""
                media_thumbs = entry.get("media_thumbnail")
                if media_thumbs:
                    thumb = media_thumbs[0].get("url", "")
                video_id = entry.get("yt_videoid", "")
                if not video_id:
                    m = re.search(r"v=([\w-]+)", entry.get("link", ""))
                    video_id = m.group(1) if m else entry.get("link", "")
                videos.append(
                    {
                        "title": entry.get("title", "(sin título)"),
                        "link": entry.get("link", "#"),
                        "video_id": video_id,
                        "channel": title,
                        "channel_id": channel_id,
                        "category": category,
                        "published_dt": pub_dt,
                        "published_iso": pub_dt.isoformat() if pub_dt else "",
                        "thumbnail": thumb,
                    }
                )
            return videos
        except Exception as exc:  # noqa: BLE001 - queremos capturar cualquier fallo de red/parseo
            if attempt < RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f"[WARN] {title} ({channel_id}) sin feed disponible: {exc}")
            return []
    return []


def load_channels() -> list[tuple[str, str, str, str]]:
    channels = []
    with open(DATA_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row["ID del canal"].strip()
            title = row["Título del canal"].strip()
            cat = row["categoria"].strip()
            logo = (row.get("logo_url") or "").strip()  # columna opcional
            if cid:
                channels.append((cid, title, cat, logo))
    return channels


def fmt_display_date(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%d %b %Y, %H:%M UTC")


def load_previous_state() -> dict[str, list[str]]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict[str, list[str]]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    channels = load_channels()
    total = len(channels)
    print(f"Canales a consultar: {total}")

    all_videos: list[dict] = []
    errores = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(fetch_channel_feed, cid, title, cat): cid
            for cid, title, cat, logo in channels
        }
        done = 0
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if not result:
                errores += 1
            all_videos.extend(result)
            done += 1
            if done % 100 == 0 or done == total:
                print(f"  progreso: {done}/{total} canales procesados")

    print(f"Videos recolectados: {len(all_videos)} (canales sin feed: {errores})")

    # --- comparar contra la ejecución anterior para saber qué canales subieron algo NUEVO ---
    previous_state = load_previous_state()
    first_run = not bool(previous_state)

    current_ids_by_channel: dict[str, list[str]] = {}
    for v in all_videos:
        current_ids_by_channel.setdefault(v["channel_id"], []).append(v["video_id"])

    channels_with_new_material: set[str] = set()
    for cid, current_ids in current_ids_by_channel.items():
        prev_ids = set(previous_state.get(cid, []))
        if not first_run and any(vid not in prev_ids for vid in current_ids):
            channels_with_new_material.add(cid)

    save_state(current_ids_by_channel)

    if first_run:
        print("Primera ejecución: aún no hay estado previo para comparar, ningún canal se marca como 'nuevo' todavía.")
    else:
        print(f"Canales con material nuevo desde la última ejecución: {len(channels_with_new_material)}")

    # ordenar globalmente por fecha, más reciente primero
    all_videos.sort(
        key=lambda v: v["published_dt"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    for v in all_videos:
        v["published_display"] = fmt_display_date(v["published_dt"])

    # agrupar por categoría
    categories: dict[str, list[dict]] = {}
    for v in all_videos:
        categories.setdefault(v["category"], []).append(v)

    # canales por categoría (todos, tengan o no videos recientes) — para la vista "Canales"
    channels_by_category: dict[str, list[dict]] = {}
    for cid, title, cat, logo in channels:
        channels_by_category.setdefault(cat, []).append(
            {
                "id": cid,
                "title": title,
                "url": f"https://www.youtube.com/channel/{cid}",
                "logo": logo,
            }
        )
    for cat in channels_by_category:
        channels_by_category[cat].sort(key=lambda c: c["title"].lower())

    # asegurar que toda categoría con canales aparezca aunque no tenga videos recientes
    for cat in channels_by_category:
        categories.setdefault(cat, [])

    category_order = sorted(categories.keys(), key=lambda c: -len(channels_by_category.get(c, [])))

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("index.html.j2")

    html = template.render(
        categories=categories,
        channels_by_category=channels_by_category,
        channels_with_new_material=channels_with_new_material,
        first_run=first_run,
        category_order=category_order,
        total_videos=len(all_videos),
        total_channels=total,
        generated_at=datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
    )

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"Listo -> {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
