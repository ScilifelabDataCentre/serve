import logging

from .schemas import AutocompleteTerm, TermMetadata

logger = logging.getLogger(__name__)


class VocabularyMemoryService:
    """In-memory vocabulary service with lazy loading from pickle files."""

    _instance = None
    _loaded = False

    def __new__(cls) -> "VocabularyMemoryService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    autocomplete_data: dict[str, list[AutocompleteTerm]]
    term_metadata: dict[str, TermMetadata]

    def __init__(self) -> None:
        if not self._loaded:
            self.autocomplete_data = {}
            self.term_metadata = {}
            self._load_vocabulary_data()
            VocabularyMemoryService._loaded = True

    def _load_vocabulary_data(self) -> None:
        """Load vocabulary data from pickle files into memory."""
        import os
        import pickle

        from django.conf import settings

        vocab_dir = getattr(
            settings, "VOCABULARY_DATA_PATH", os.path.join(settings.BASE_DIR, "common", "data", "invernio_keywords")
        )

        sources = ["mesh", "euroscivoc", "gemet"]

        for source in sources:
            try:
                # Load autocomplete data
                autocomplete_file = os.path.join(vocab_dir, f"{source}_autocomplete.pickle")
                if os.path.exists(autocomplete_file):
                    with open(autocomplete_file, "rb") as f:
                        source_autocomplete = pickle.load(f)

                    # Merge with global autocomplete data
                    for prefix, terms in source_autocomplete.items():
                        if prefix not in self.autocomplete_data:
                            self.autocomplete_data[prefix] = []
                        # Convert dicts to AutocompleteTerm models
                        self.autocomplete_data[prefix].extend(
                            [
                                AutocompleteTerm(**term) if not isinstance(term, AutocompleteTerm) else term
                                for term in terms
                            ]
                        )

                # Load term metadata
                terms_file = os.path.join(vocab_dir, f"{source}_terms.pickle")
                if os.path.exists(terms_file):
                    with open(terms_file, "rb") as f:
                        source_terms = pickle.load(f)

                    # Store with source prefix to avoid ID conflicts
                    for term_id, term_data in source_terms.items():
                        if isinstance(term_data, dict):
                            self.term_metadata[f"{source}:{term_id}"] = TermMetadata(**term_data)
                        else:
                            self.term_metadata[f"{source}:{term_id}"] = term_data

            except Exception as e:
                logger.error(f"Failed to load {source} vocabulary: {e}")

        # Sort combined autocomplete data
        for prefix, terms in self.autocomplete_data.items():
            terms.sort(key=lambda x: (x.score, x.label))

        logger.info(f"Loaded vocabulary: {len(self.term_metadata)} terms, " f"{len(self.autocomplete_data)} prefixes")

    def search_subjects(self, query: str, limit: int = 10) -> list[AutocompleteTerm]:
        """Search for subject keywords with autocomplete suggestions."""
        if not query:
            return []

        query_lower = query.lower().strip()
        if len(query_lower) < 2:  # Minimum query length
            return []

        suggestions: list[AutocompleteTerm] = []

        # Look for exact prefix matches first
        for prefix_len in range(len(query_lower), 1, -1):
            prefix = query_lower[:prefix_len]
            if prefix in self.autocomplete_data:
                # Filter terms that contain the full query
                for term in self.autocomplete_data[prefix]:
                    if query_lower in term.label.lower():
                        suggestions.append(term)
                break

        # Sort by relevance: exact matches first, then by score
        suggestions.sort(
            key=lambda x: (
                0 if x.label.lower().startswith(query_lower) else 1,
                x.score,
                x.label,
            )
        )

        return suggestions[:limit]

    def get_term_details(self, term_id: str) -> TermMetadata | None:
        """Get detailed information about a specific term."""
        return self.term_metadata.get(term_id)

    def is_loaded(self) -> bool:
        """Check if vocabulary data has been loaded."""
        return self._loaded and bool(self.autocomplete_data)
