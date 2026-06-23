"""GPU capacity checks for user apps.

The cluster has a limited number of GPUs (settings.GPU_TOTAL_CAPACITY). Instead of
querying kubernetes, GPU usage is derived from the database: every non-deleted app
instance whose app template is gpu_enabled and whose flavor requests a GPU is
considered to hold that GPU.
"""

from django.conf import settings

from studio.utils import get_logger

logger = get_logger(__name__)

GPU_UNAVAILABLE_MESSAGE = (
    "All GPUs are currently in use. You can launch an app on a GPU later, when one becomes available."
)


class GpuUnavailableError(Exception):
    """Raised when an app requests a GPU but the cluster has none available."""

    def __init__(self, message: str = GPU_UNAVAILABLE_MESSAGE):
        self.ui_error = message
        super().__init__(message)


def flavor_gpu_count(flavor) -> int:
    """Number of GPUs a flavor requests."""
    if flavor is None or not flavor.gpu_req:
        return 0
    return max(flavor.gpu_req, 0)


def instance_holds_gpu(instance) -> bool:
    """Whether an app instance actually allocates a GPU (gpu-enabled app template + GPU flavor)."""
    return instance.app.gpu_enabled and flavor_gpu_count(instance.flavor) > 0


def gpus_in_use(exclude_instance=None) -> int:
    """Total number of GPUs requested by active (not deleted) app instances.

    Pass exclude_instance when re-evaluating an existing app so the GPU it
    already holds is not counted.
    """
    from apps.app_registry import APP_REGISTRY

    total = 0
    # Use a set since some models are registered under multiple slugs (e.g. shiny apps)
    for orm_model in set(APP_REGISTRY.iter_orm_models()):
        queryset = (
            orm_model.objects.filter(app__gpu_enabled=True, flavor__isnull=False)
            .exclude(latest_user_action__in=["Deleting", "SystemDeleting"])
            .select_related("flavor", "app")
        )
        if exclude_instance is not None and exclude_instance.pk is not None and isinstance(exclude_instance, orm_model):
            queryset = queryset.exclude(pk=exclude_instance.pk)
        total += sum(flavor_gpu_count(instance.flavor) for instance in queryset)
    return total


def gpu_available_for_flavor(flavor, exclude_instance=None) -> bool:
    """Whether the cluster has enough free GPUs to satisfy the given flavor."""
    requested = flavor_gpu_count(flavor)
    if requested == 0:
        return True
    return gpus_in_use(exclude_instance=exclude_instance) + requested <= settings.GPU_TOTAL_CAPACITY


def ensure_gpu_capacity(instance) -> None:
    """Lock and re-check GPU capacity."""
    from apps.models import Apps

    if not (instance.app.gpu_enabled and flavor_gpu_count(instance.flavor) > 0):
        return

    # Serialize concurrent GPU submissions before recounting capacity.
    list(Apps.objects.select_for_update().filter(gpu_enabled=True).order_by("pk"))

    if not gpu_available_for_flavor(instance.flavor, exclude_instance=instance):
        logger.info(
            "GPU capacity gate rejected app instance pk=%s flavor=%s: %s of %s GPUs in use",
            instance.pk,
            instance.flavor_id,
            gpus_in_use(exclude_instance=instance),
            settings.GPU_TOTAL_CAPACITY,
        )
        raise GpuUnavailableError()


def model_class_gpu_enabled(model_class) -> bool:
    """Whether any app template served by the given app instance model is gpu_enabled."""
    from apps.app_registry import APP_REGISTRY
    from apps.models import Apps

    slugs = [slug for slug, entry in APP_REGISTRY.get_apps().items() if entry.Model is model_class]
    return Apps.objects.filter(slug__in=slugs, gpu_enabled=True).exists()
