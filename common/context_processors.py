from .models import MaintenanceMode


def maintenance_mode(request):
    data = MaintenanceMode.objects.all()
    return {"maintenance_mode": data}
