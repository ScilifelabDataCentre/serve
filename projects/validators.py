from django.core.exceptions import ValidationError


def validate_image_content_type(image):
    if image.content_type not in ["image/jpeg", "image/png"]:
        raise ValidationError(code="unsupported_content_type" "Unsupported content type")


def validate_limit_not_below_request(resource, limit, request, unit):
    """Check a hardware limit against its fixed request.

    Kubernetes rejects a pod whose request exceeds its limit. Returns a description of
    the problem, or None when the limit is usable.
    """
    try:
        amount = float(limit)
    except (TypeError, ValueError):
        return f"{resource}: '{limit}' is not a number."

    if amount < request:
        return f"{resource}: the limit cannot be lower than the request of {request}{unit}."

    return None
