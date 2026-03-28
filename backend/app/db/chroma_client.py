"""
ChromaDB service — single access point for all vector store operations.
Four collections:
  - dnd5e_rules    → core rules, conditions, combat, resting
  - dnd5e_spells   → full SRD spell list
  - dnd5e_monsters → CR, stats, abilities
  - dnd5e_equipment → weapons, armour, gear tables
  - dnd5e_classes  → class features, subclasses
  - narrative_memory → per-session compressed story beats (Archivist agent)

All collections use ChromaDB's built-in embedding function (no external
embedding API needed — embeddings run locally via chromadb's default
all-MiniLM-L6-v2 model which downloads once on first run, ~90MB).
"""

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings
from chromadb.config import Settings

client = chromadb.PersistentClient(
    path="./your_db_path", 
    settings=Settings(anonymized_telemetry=False) # Add this!
)

# ── Client singleton ──────────────────────────────────────────────────────────

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_PATH,
        )
    return _client


# ── Embedding function (local, no API key) ────────────────────────────────────

def get_embedding_fn() -> embedding_functions.SentenceTransformerEmbeddingFunction:
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


# ── Collection names ──────────────────────────────────────────────────────────

COLLECTION_RULES     = "dnd5e_rules"
COLLECTION_SPELLS    = "dnd5e_spells"
COLLECTION_MONSTERS  = "dnd5e_monsters"
COLLECTION_EQUIPMENT = "dnd5e_equipment"
COLLECTION_CLASSES   = "dnd5e_classes"
COLLECTION_MEMORY    = "narrative_memory"

ALL_GAME_COLLECTIONS = [
    COLLECTION_RULES,
    COLLECTION_SPELLS,
    COLLECTION_MONSTERS,
    COLLECTION_EQUIPMENT,
    COLLECTION_CLASSES,
]


# ── ChromaService ─────────────────────────────────────────────────────────────

class ChromaService:
    """
    Wraps all ChromaDB read/write operations.
    Instantiated once in rules_lawyer.py and event_bus.py.
    """

    def __init__(self) -> None:
        self._client   = get_client()
        self._embed_fn = get_embedding_fn()
        self._collections: dict[str, chromadb.Collection] = {}

    def _get_collection(self, name: str) -> chromadb.Collection:
        """Get or create a collection (cached after first access)."""
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                embedding_function=self._embed_fn,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[name]

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        collection_name: str,
        query_text: str,
        top_k: int | None = None,
    ) -> list[str]:
        """
        Semantic search a single collection.
        Returns a list of matching document strings.
        """
        k = top_k or settings.RAG_TOP_K
        col = self._get_collection(collection_name)

        # Guard: don't query an empty collection
        if col.count() == 0:
            return []

        results = col.query(
            query_texts=[query_text],
            n_results=min(k, col.count()),
        )
        docs = results.get("documents", [[]])[0]
        return docs

    def query_all_game_collections(
        self,
        query_text: str,
        top_k_per_collection: int = 2,
    ) -> str:
        """
        Query all five game collections simultaneously and merge results.
        Returns a single formatted string ready for DM prompt injection.
        Used by RulesLawyer so one call covers rules + spells + monsters.
        """
        all_chunks: list[str] = []

        for col_name in ALL_GAME_COLLECTIONS:
            chunks = self.query(col_name, query_text, top_k=top_k_per_collection)
            all_chunks.extend(chunks)

        if not all_chunks:
            return ""

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for chunk in all_chunks:
            if chunk not in seen:
                seen.add(chunk)
                unique.append(chunk)

        return "\n\n---\n\n".join(unique)

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert(
        self,
        collection_name: str,
        documents: list[str],
        ids: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        """
        Insert or update documents in a collection.
        Used by ingest.py and the Archivist agent.
        """
        col = self._get_collection(collection_name)
        col.upsert(
            documents=documents,
            ids=ids,
            metadatas=metadatas or [{} for _ in documents],
        )

    def count(self, collection_name: str) -> int:
        """Return number of documents in a collection."""
        return self._get_collection(collection_name).count()

    def collection_stats(self) -> dict[str, int]:
        """Return document counts for all collections — useful for health check."""
        return {name: self.count(name) for name in ALL_GAME_COLLECTIONS + [COLLECTION_MEMORY]}

    # ── Narrative memory (Archivist) ──────────────────────────────────────────

    def store_memory(
        self,
        session_id: str,
        turn_number: int,
        compressed_text: str,
    ) -> None:
        """
        Store a compressed narrative beat in long-term memory.
        Called by the Archivist agent every N turns.
        """
        self.upsert(
            collection_name=COLLECTION_MEMORY,
            documents=[compressed_text],
            ids=[f"{session_id}_turn_{turn_number}"],
            metadatas=[{"session_id": session_id, "turn": turn_number}],
        )

    def recall_memory(self, query: str, session_id: str, top_k: int = 3) -> list[str]:
        """
        Retrieve relevant past narrative beats for a session.
        Used by DM Agent to prevent context rot on long campaigns.
        """
        col = self._get_collection(COLLECTION_MEMORY)
        if col.count() == 0:
            return []

        results = col.query(
            query_texts=[query],
            n_results=min(top_k, col.count()),
            where={"session_id": session_id},
        )
        return results.get("documents", [[]])[0]


# Singleton
chroma_service = ChromaService()