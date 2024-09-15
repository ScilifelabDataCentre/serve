from studio.utils import get_logger

from .models import MaintenanceMode

logger = get_logger(__name__)


def maintenance_mode(request):
    try:
        data = MaintenanceMode.objects.all()
    except Exception as e:
        logger.debug("Error fetching maintenance mode data: %s", e)
        data = []
    return {"maintenance_mode": data}
