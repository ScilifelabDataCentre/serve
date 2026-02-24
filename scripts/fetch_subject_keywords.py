#!/usr/bin/env python
"""
Standalone script to collect vocabulary keywords from MeSH, EuroSciVoc, and GEMET.
Stores data as binary files using pickle for fast in-memory loading.
"""

import argparse
import json
import logging
import os
import pickle
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add Django project to path if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def collect_vocabulary_keywords(sources_filter=None, vocab_dir=None):
    """Collect keywords from specified sources and store as binary files.

    Args:
        sources_filter: List of source names to collect. If None, collect from all sources.
                       Valid sources: ['euroscivoc', 'gemet', 'mesh']
        vocab_dir: Directory path to store vocabulary data. If None, use current directory.
    """

    # Source configurations - all sources available
    all_sources = {
        "mesh": {
            "url": "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2026.xml",
            "parser": parse_mesh_xml_gz,
            "scheme_name": "Medical Subject Headings",
            "scheme_uri": "https://meshb.nlm.nih.gov/",
            "value_uri_template": "https://id.nlm.nih.gov/mesh/{id}",
        },
        "euroscivoc": {
            "url": (
                "https://op.europa.eu/o/opportal-service/"
                "euvoc-download-handler?cellarURI="
                "http%3A%2F%2Fpublications.europa.eu%2Fresource%2Fdistribution%2Feuroscivoc%2F20250924"
                "-0%2Frdf%2Fskos_xl%2FEuroSciVoc.rdf"
                "&fileName=EuroSciVoc.rdf"
            ),
            "parser": parse_euroscivoc_rdf,
            "scheme_name": "EuroSciVoc The European Science Vocabulary",
            "scheme_uri": "http://data.europa.eu/8mn/euroscivoc/",
            "value_uri_template": "http://data.europa.eu/8mn/euroscivoc/{id}",
        },
        "gemet": {
            "url": "https://www.eionet.europa.eu/gemet/latest/gemet.rdf.gz",
            "parser": parse_gemet_rdf_gz,
            "scheme_name": "GEMET Environmental Thesaurus",
            "scheme_uri": "https://www.eionet.europa.eu/gemet/",
            "value_uri_template": "https://www.eionet.europa.eu/gemet/concept/{id}",
        },
    }

    # Filter sources based on input
    if sources_filter:
        sources = {k: v for k, v in all_sources.items() if k in sources_filter}
        if not sources:
            logger.error(f"No valid sources found. Available sources: {list(all_sources.keys())}")
            return 0
        logger.info(f"Processing sources: {list(sources.keys())}")
    else:
        sources = all_sources
        logger.info("Processing all sources")

    total_stored = 0

    for source_name, config in sources.items():
        try:
            logger.info(f"Collecting {source_name} keywords...")
            keywords = config["parser"](config)
            count = store_keywords_as_binary(source_name, keywords, config, vocab_dir)
            total_stored += count
            logger.info(f"Stored {count} {source_name} keywords")
        except Exception as e:
            logger.error(f"Failed to collect {source_name}: {e}")

    logger.info(f"Total keywords stored: {total_stored}")
    return total_stored


def parse_mesh_xml_gz(config):
    """Parse MeSH XML file (handles both gzipped and regular XML)."""
    import gzip
    import xml.etree.ElementTree as ET

    import requests

    try:
        logger.info("Downloading MeSH descriptor file...")

        # Use streaming download for large files
        response = requests.get(config["url"], timeout=60, stream=True)
        response.raise_for_status()

        # Get file size for progress
        total_size = int(response.headers.get("content-length", 0))
        logger.info(f"File size: {total_size / (1024*1024):.1f} MB")

        # Download with progress
        content = b""
        downloaded = 0

        for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            if chunk:
                content += chunk
                downloaded += len(chunk)

                if total_size > 0:
                    progress = (downloaded / total_size) * 100
                    logger.info(f"Downloaded: {downloaded / (1024*1024):.1f} MB ({progress:.1f}%)")
                else:
                    logger.info(f"Downloaded: {downloaded / (1024*1024):.1f} MB")

        logger.info("Download complete, processing...")

        # Check if content is actually gzipped
        if content.startswith(b"\x1f\x8b"):  # Gzip magic number
            logger.info("Decompressing gzipped MeSH data...")
            xml_content = gzip.decompress(content)
        elif content.startswith(b"<?xml"):  # XML header
            logger.info("Processing uncompressed XML data...")
            xml_content = content
        else:
            # Try to decompress anyway, fallback to raw content
            try:
                logger.info("Attempting to decompress...")
                xml_content = gzip.decompress(content)
            except Exception:
                logger.info("Using raw content as XML...")
                xml_content = content

        # Parse XML
        logger.info("Parsing MeSH XML...")
        root = ET.fromstring(xml_content)

        keywords = []

        for descriptor in root.findall("DescriptorRecord"):
            try:
                # Get MeSH ID (DescriptorUI)
                ui_element = descriptor.find("DescriptorUI")
                if ui_element is None:
                    continue
                mesh_id = ui_element.text

                # Get preferred term (DescriptorName/String)
                name_element = descriptor.find("DescriptorName/String")
                if name_element is None:
                    continue
                label = name_element.text

                keywords.append({"id": mesh_id, "label": label})

            except Exception as e:
                logger.warning(f"Error parsing MeSH descriptor: {e}")
                continue

        logger.info(f"Parsed {len(keywords)} MeSH descriptors")
        return keywords

    except Exception as e:
        logger.error(f"Failed to process MeSH data: {e}")
        raise


def parse_euroscivoc_rdf(config):
    """Parse EuroSciVoc SKOS-XL RDF file."""
    import xml.etree.ElementTree as ET

    import requests

    # RDF/SKOS namespace mappings
    namespaces = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "skosxl": "http://www.w3.org/2008/05/skos-xl#",
        "dct": "http://purl.org/dc/terms/",
    }

    # Register namespaces for ElementTree
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)

    try:
        logger.info("Downloading EuroSciVoc RDF file...")
        response = requests.get(config["url"], timeout=300)  # 5 minute timeout
        response.raise_for_status()

        # Parse RDF XML
        logger.info("Parsing EuroSciVoc RDF...")
        root = ET.fromstring(response.content)

        # First pass: Build a map of label URIs to their text values
        label_map = {}
        for description in root.findall(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
            # Check if this is a SKOS-XL Label
            type_elem = description.find(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}type")
            if type_elem is not None:
                type_resource = type_elem.get(f'{{{namespaces["rdf"]}}}resource')
                if type_resource and "skos-xl#Label" in type_resource:
                    about_uri = description.get(f'{{{namespaces["rdf"]}}}about')
                    literal_form = description.find(".//{http://www.w3.org/2008/05/skos-xl#}literalForm")
                    if about_uri and literal_form is not None and literal_form.text:
                        lang = literal_form.get("{http://www.w3.org/XML/1998/namespace}lang", "en")
                        if about_uri not in label_map:
                            label_map[about_uri] = {}
                        label_map[about_uri][lang] = literal_form.text.strip()

        logger.info(f"Built label map with {len(label_map)} labels")

        # Second pass: Find concepts and their labels
        keywords = []
        for description in root.findall(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description"):
            try:
                # Check if this is a skos:Concept
                type_elem = description.find(".//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}type")
                if type_elem is None:
                    continue

                type_resource = type_elem.get(f'{{{namespaces["rdf"]}}}resource')
                if not type_resource or "skos/core#Concept" not in type_resource:
                    continue

                # Get concept URI from rdf:about attribute
                about_uri = description.get(f'{{{namespaces["rdf"]}}}about')
                if not about_uri:
                    continue

                # Extract UUID from URI (last part after /)
                concept_id = about_uri.split("/")[-1]

                # Get preferred label (try English first, then any language)
                pref_label = None
                pref_label_elems = description.findall(".//{http://www.w3.org/2008/05/skos-xl#}prefLabel")

                for pref_label_elem in pref_label_elems:
                    label_uri = pref_label_elem.get(f'{{{namespaces["rdf"]}}}resource')
                    if label_uri and label_uri in label_map:
                        # Prefer English
                        if "en" in label_map[label_uri]:
                            pref_label = label_map[label_uri]["en"]
                            break
                        # Fallback to any available language
                        elif label_map[label_uri]:
                            pref_label = list(label_map[label_uri].values())[0]
                            break

                if concept_id and pref_label:
                    keywords.append({"id": concept_id, "label": pref_label})

            except Exception as e:
                logger.warning(f"Error parsing EuroSciVoc concept: {e}")
                continue

        logger.info(f"Parsed {len(keywords)} EuroSciVoc concepts")
        return keywords

    except Exception as e:
        logger.error(f"Failed to process EuroSciVoc data: {e}")
        raise


def parse_gemet_rdf_gz(config):
    """Parse GEMET using their REST API to get ALL concepts."""
    import json

    import requests

    try:
        logger.info("Fetching ALL GEMET concepts via API...")

        # Use GEMET API to get ALL concepts with wildcard search
        api_url = "http://www.eionet.europa.eu/gemet/getConceptsMatchingKeyword"

        # Try searches to get more concepts
        all_concepts = {}  # Use dict to avoid duplicates

        # Search for common letters to capture all concepts
        search_terms = [
            "a",
            "e",
            "i",
            "o",
            "u",
            "b",
            "c",
            "d",
            "f",
            "g",
            "h",
            "j",
            "k",
            "l",
            "m",
            "n",
            "p",
            "q",
            "r",
            "s",
            "t",
            "v",
            "w",
            "x",
            "y",
            "z",
        ]

        for term in search_terms:
            try:
                params = {
                    "keyword": term,
                    "search_mode": 3,  # prefix/suffix combined (%keyword%)
                    "thesaurus_uri": "http://www.eionet.europa.eu/gemet/concept/",
                    "language": "en",
                }

                response = requests.get(api_url, params=params, timeout=60)
                response.raise_for_status()

                term_concepts = response.json()
                logger.info(f"Found {len(term_concepts)} concepts matching '{term}'")

                # Add to master list (dict will handle duplicates)
                for concept in term_concepts:
                    concept_uri = concept.get("uri", "")
                    if concept_uri:
                        all_concepts[concept_uri] = concept

            except Exception as e:
                logger.warning(f"Failed to fetch concepts for term '{term}': {e}")
                continue

        logger.info(f"Total unique concepts found: {len(all_concepts)}")

        keywords = []

        # Process each unique concept
        for concept in all_concepts.values():
            try:
                # Extract concept ID from URI
                concept_uri = concept.get("uri", "")
                if not concept_uri or "/concept/" not in concept_uri:
                    continue

                concept_id = concept_uri.split("/concept/")[-1]
                pref_label = concept.get("preferredLabel", {}).get("string", "")

                if concept_id and pref_label:
                    keywords.append({"id": concept_id, "label": pref_label.strip()})

            except Exception as e:
                logger.warning(f"Error parsing GEMET concept: {e}")
                continue

        logger.info(f"Parsed {len(keywords)} GEMET concepts")
        return keywords

    except Exception as e:
        logger.error(f"Failed to process GEMET data: {e}")
        raise


def store_keywords_as_binary(
    source: str, keywords: List[Dict[str, Any]], config: Dict[str, Any], vocab_dir: Optional[str] = None
) -> int:
    """Store keywords as binary files with efficient autocomplete structure using pickle."""

    # Use provided directory or create default timestamped one
    if vocab_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        vocab_dir = os.path.join(os.path.dirname(__file__), f"vocabulary_data_{timestamp}")

    # Create directory if it doesn't exist
    os.makedirs(vocab_dir, exist_ok=True)

    # Store individual keywords with full metadata
    keyword_count = 0
    autocomplete_data: Dict[str, List[Dict[str, Any]]] = {}
    term_metadata: Dict[str, Dict[str, Any]] = {}

    for keyword in keywords:
        # Create complete subject data
        subject_data = {
            "subject": keyword["label"],
            "subject_scheme": config["scheme_name"],
            "scheme_uri": config["scheme_uri"],
            "value_uri": config["value_uri_template"].format(id=keyword["id"]),
            "classification_code": keyword["id"],
            "lang": "en",
        }

        # Store full metadata for later lookup
        term_metadata[keyword["id"]] = subject_data

        # Build autocomplete index by prefix
        label_lower = keyword["label"].lower()
        for i in range(2, min(len(label_lower) + 1, 10)):  # Prefixes 2-10 chars
            prefix = label_lower[:i]
            if prefix not in autocomplete_data:
                autocomplete_data[prefix] = []

            autocomplete_data[prefix].append(
                {
                    "id": keyword["id"],
                    "label": keyword["label"],
                    "source": source,
                    "score": len(keyword["label"]),  # For sorting by length
                }
            )

        keyword_count += 1

    # Sort autocomplete indices
    for prefix, terms in autocomplete_data.items():
        terms.sort(key=lambda x: (x["score"], x["label"]))

    # Write binary files using pickle
    logger.info(f"Writing {source} binary files...")

    with open(os.path.join(vocab_dir, f"{source}_terms.pickle"), "wb") as f:
        pickle.dump(term_metadata, f, protocol=pickle.HIGHEST_PROTOCOL)

    with open(os.path.join(vocab_dir, f"{source}_autocomplete.pickle"), "wb") as f:
        pickle.dump(autocomplete_data, f, protocol=pickle.HIGHEST_PROTOCOL)

    # Write metadata
    metadata = {
        "source": source,
        "term_count": keyword_count,
        "config": {
            "scheme_name": config["scheme_name"],
            "scheme_uri": config["scheme_uri"],
            "value_uri_template": config["value_uri_template"],
        },
        "created_at": datetime.now().isoformat(),
    }

    with open(os.path.join(vocab_dir, f"{source}_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Completed {source}: {keyword_count} terms")
    return keyword_count


if __name__ == "__main__":
    """Run the vocabulary collection script."""

    parser = argparse.ArgumentParser(
        description="Collect vocabulary keywords from various sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_subject_keywords.py --sources gemet
  python fetch_subject_keywords.py --sources euroscivoc gemet
  python fetch_subject_keywords.py --sources all
  python fetch_subject_keywords.py  # all sources (default)
        """,
    )

    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["euroscivoc", "gemet", "mesh", "all"],
        default=["all"],
        help="Specify which vocabulary sources to process (default: all)",
    )

    args = parser.parse_args()

    # Handle 'all' argument
    if "all" in args.sources:
        sources_filter = None  # Process all sources
    else:
        sources_filter = args.sources

    logger.info("Starting vocabulary collection...")

    # Create single timestamped directory for this run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    vocab_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"vocabulary_data_{timestamp}")
    os.makedirs(vocab_dir, exist_ok=True)

    logger.info(f"Data will be saved to: vocabulary_data_{timestamp}")

    try:
        total = collect_vocabulary_keywords(sources_filter, vocab_dir)
        logger.info(f"Successfully processed {total} vocabulary terms")
        logger.info(f"Vocabulary data saved to ./vocabulary_data_{timestamp}/")

    except KeyboardInterrupt:
        logger.info("Collection interrupted by user")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Collection failed: {e}")
        sys.exit(1)
