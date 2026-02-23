from django.http import HttpRequest, JsonResponse
from rest_framework.decorators import api_view, permission_classes

from studio.utils import get_logger

logger = get_logger(__name__)


@api_view(["GET"])  # type: ignore[misc]
@permission_classes(())  # type: ignore[misc]
def keyword_search(request: HttpRequest) -> JsonResponse:
    """API endpoint to search vocabulary terms for subject autocomplete"""
    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({"suggestions": []})

    try:
        # Use vocabulary service for search
        from doi_minting.services.keywords_service import VocabularyMemoryService

        service = VocabularyMemoryService()

        # Search for terms
        suggestions = service.search_subjects(query, limit=10)

        # Format results for frontend - just return the labels as strings
        results = []
        for term in suggestions:
            results.append(term.label)  # JavaScript expects simple string array

        return JsonResponse({"suggestions": results})

    except Exception as e:
        logger.error(f"Vocabulary search error: {e}")
        return JsonResponse({"suggestions": [], "error": str(e)}, status=500)
