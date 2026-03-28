"""
ingest.py — one-shot D&D 5e SRD ingestion script.
Run once from the backend/ directory:
    python -m scripts.ingest

Sources:
  - open5e.com public API  → spells, monsters, equipment, classes
  - data/srd_rules.md      → core rules (you provide this file)

Progress is printed to stdout. Safe to re-run — uses upsert so no duplicates.
Estimated time: 3-8 minutes depending on internet speed and CPU.
"""

import hashlib
import sys
import time
from pathlib import Path

import httpx

# Add backend/ to path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.chroma_client import (
    chroma_service,
    COLLECTION_RULES,
    COLLECTION_SPELLS,
    COLLECTION_MONSTERS,
    COLLECTION_EQUIPMENT,
    COLLECTION_CLASSES,
)

OPEN5E_BASE = "https://api.open5e.com/v1"
REQUEST_DELAY = 0.3   # seconds between API calls — be polite to the free API


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_id(text: str) -> str:
    """Stable deterministic ID from content hash."""
    return hashlib.md5(text.encode()).hexdigest()


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 60) -> list[str]:
    """
    Split text into overlapping chunks for better semantic retrieval.
    chunk_size and overlap are in characters (not tokens).
    """
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def fetch_all_pages(endpoint: str, params: dict | None = None) -> list[dict]:
    """
    Paginate through an open5e endpoint and return all results.
    open5e uses ?limit=&offset= pagination.
    """
    all_results: list[dict] = []
    url = f"{OPEN5E_BASE}/{endpoint}/"
    page_params = {"limit": 100, "offset": 0, **(params or {})}

    with httpx.Client(timeout=30) as client:
        while url:
            resp = client.get(url, params=page_params)
            resp.raise_for_status()
            data = resp.json()
            all_results.extend(data.get("results", []))
            url = data.get("next")
            page_params = {}  # next URL already has params baked in
            time.sleep(REQUEST_DELAY)

    return all_results


def upsert_batch(
    collection: str,
    documents: list[str],
    metadatas: list[dict],
) -> None:
    ids = [make_id(doc) for doc in documents]
    chroma_service.upsert(collection, documents, ids, metadatas)


# ── Ingestors ─────────────────────────────────────────────────────────────────

def ingest_spells() -> None:
    print("\n[Spells] Fetching from open5e...")
    spells = fetch_all_pages("spells", {"document__slug": "wotc-srd"})
    print(f"[Spells] {len(spells)} spells fetched. Ingesting...")

    docs: list[str]  = []
    metas: list[dict] = []

    for spell in spells:
        text = (
            f"Spell: {spell.get('name', '')}\n"
            f"Level: {spell.get('level_int', '?')} | "
            f"School: {spell.get('school', '?')} | "
            f"Casting Time: {spell.get('casting_time', '?')}\n"
            f"Range: {spell.get('range', '?')} | "
            f"Components: {spell.get('components', '?')} | "
            f"Duration: {spell.get('duration', '?')}\n"
            f"Description: {spell.get('desc', '')}\n"
            f"Higher Levels: {spell.get('higher_level', '')}"
        ).strip()

        docs.append(text)
        metas.append({
            "type": "spell",
            "name": spell.get("name", ""),
            "level": spell.get("level_int", 0),
        })

    upsert_batch(COLLECTION_SPELLS, docs, metas)
    print(f"[Spells] Done. {len(docs)} documents stored.")


def ingest_monsters() -> None:
    print("\n[Monsters] Fetching from open5e...")
    monsters = fetch_all_pages("monsters", {"document__slug": "wotc-srd"})
    print(f"[Monsters] {len(monsters)} monsters fetched. Ingesting...")

    docs: list[str]  = []
    metas: list[dict] = []

    for m in monsters:
        # Build a concise stat block string
        actions = " | ".join(
            f"{a.get('name','')}: {a.get('desc','')[:120]}"
            for a in (m.get("actions") or [])[:3]
        )
        text = (
            f"Monster: {m.get('name', '')}\n"
            f"CR: {m.get('challenge_rating', '?')} | "
            f"Type: {m.get('type', '?')} | "
            f"Size: {m.get('size', '?')} | "
            f"Alignment: {m.get('alignment', '?')}\n"
            f"HP: {m.get('hit_points', '?')} | "
            f"AC: {m.get('armor_class', '?')} | "
            f"Speed: {m.get('speed', '?')}\n"
            f"STR {m.get('strength','?')} DEX {m.get('dexterity','?')} "
            f"CON {m.get('constitution','?')} "
            f"INT {m.get('intelligence','?')} WIS {m.get('wisdom','?')} "
            f"CHA {m.get('charisma','?')}\n"
            f"Actions: {actions}"
        ).strip()

        docs.append(text)
        metas.append({
            "type": "monster",
            "name": m.get("name", ""),
            "cr":   str(m.get("challenge_rating", "0")),
        })

    upsert_batch(COLLECTION_MONSTERS, docs, metas)
    print(f"[Monsters] Done. {len(docs)} documents stored.")


def ingest_equipment() -> None:
    print("\n[Equipment] Fetching from open5e...")
    items = fetch_all_pages("weapons", {"document__slug": "wotc-srd"})
    armour = fetch_all_pages("armor", {"document__slug": "wotc-srd"})
    all_items = items + armour
    print(f"[Equipment] {len(all_items)} items fetched. Ingesting...")

    docs: list[str]  = []
    metas: list[dict] = []

    for item in all_items:
        # 1. Grab and format the properties FIRST
        properties = item.get('properties')
        properties_str = ', '.join(properties) if isinstance(properties, list) else str(properties or 'None')

        # 2. THEN build your string
        text = (
            f"Item: {item.get('name', '')}\n"
            f"Category: {item.get('category', '?')} | "
            f"Cost: {item.get('cost', '?')} | "
            f"Weight: {item.get('weight', '?')}\n"
            f"Damage: {item.get('damage_dice', '')} {item.get('damage_type', '')}\n"
            f"Properties: {properties_str}\n"
            f"Description: {item.get('desc', '')}"
        ).strip()

        docs.append(text)
        metas.append({
            "type": "equipment",
            "name": item.get("name", ""),
        })

    upsert_batch(COLLECTION_EQUIPMENT, docs, metas)
    print(f"[Equipment] Done. {len(docs)} documents stored.")


def ingest_classes() -> None:
    print("\n[Classes] Fetching from open5e...")
    classes = fetch_all_pages("classes", {"document__slug": "wotc-srd"})
    print(f"[Classes] {len(classes)} classes fetched. Ingesting...")

    docs: list[str]  = []
    metas: list[dict] = []

    for cls in classes:
        # Base class chunk
        base_text = (
            f"Class: {cls.get('name', '')}\n"
            f"Hit Die: d{cls.get('hit_dice', '?')} | "
            f"Primary Ability: {cls.get('primary_ability', '?')}\n"
            f"Saving Throws: {cls.get('saving_throws', '?')}\n"
            f"Description: {cls.get('desc', '')[:600]}"
        ).strip()
        docs.append(base_text)
        metas.append({"type": "class", "name": cls.get("name", "")})

        # Each subclass as a separate chunk
        for sub in cls.get("archetypes", []):
            sub_text = (
                f"Subclass: {sub.get('name', '')} ({cls.get('name', '')})\n"
                f"{sub.get('desc', '')[:600]}"
            ).strip()
            docs.append(sub_text)
            metas.append({
                "type": "subclass",
                "name": sub.get("name", ""),
                "class": cls.get("name", ""),
            })

    upsert_batch(COLLECTION_CLASSES, docs, metas)
    print(f"[Classes] Done. {len(docs)} documents stored.")


def ingest_rules_from_markdown(md_path: str) -> None:
    """
    Chunk a local markdown SRD file and store in dnd5e_rules.
    The file should be the D&D 5e SRD core rules in markdown format.
    Download from: https://github.com/5e-bits/5e-database (SRD_CC_v5.1.md)
    """
    path = Path(md_path)
    if not path.exists():
        print(f"\n[Rules] WARNING: {md_path} not found. Skipping core rules.")
        print("[Rules] Download SRD_CC_v5.1.md from https://github.com/5e-bits/5e-database")
        print("[Rules] and place it at backend/data/srd_rules.md")
        return

    print(f"\n[Rules] Reading {md_path}...")
    text = path.read_text(encoding="utf-8")
    chunks = chunk_text(text, chunk_size=500, overlap=80)
    print(f"[Rules] {len(chunks)} chunks created. Ingesting...")

    docs  = chunks
    metas = [{"type": "rule", "source": "srd_cc_v5.1"} for _ in chunks]
    upsert_batch(COLLECTION_RULES, docs, metas)
    print(f"[Rules] Done. {len(docs)} documents stored.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Chronicles of the Forgotten Realm — SRD Ingestor")
    print("=" * 60)

    # Check existing state
    stats = chroma_service.collection_stats()
    print("\nCurrent collection state:")
    for name, count in stats.items():
        print(f"  {name}: {count} documents")

    print("\nStarting ingestion (this will take 3-8 minutes)...")
    t_start = time.time()

    ingest_spells()
    ingest_monsters()
    ingest_equipment()
    ingest_classes()
    ingest_rules_from_markdown("data/srd_rules.md")

    elapsed = int(time.time() - t_start)
    print("\n" + "=" * 60)
    print(f"Ingestion complete in {elapsed}s.")

    # Final counts
    stats = chroma_service.collection_stats()
    print("\nFinal collection state:")
    for name, count in stats.items():
        print(f"  {name}: {count} documents")
    print("=" * 60)


if __name__ == "__main__":
    main()