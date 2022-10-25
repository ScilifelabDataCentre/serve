from django.conf import settings
from django.http import JsonResponse

from apps.models import Apps, AppInstance
from django.db.models import Q

def get_studio_settings(request):
    """
    This view should return a list of settings
    needed to set up the CLI client.
    """
    studio_settings = []

    studio_url = {
        "name": "studio_host",
        "value": settings.STUDIO_HOST
    }
    kc_url = {
        "name": "keycloak_host",
        "value": settings.KC_URL
    }

    studio_settings.append(studio_url)
    studio_settings.append(kc_url)

    return JsonResponse({'data': studio_settings})

def list_apps(request):
        list_apps = list(AppInstance.objects.filter(~Q(state='Deleted'), access='public').order_by('-updated_on')[:8].values('id','name','app_id','table_field','description','updated_on'))
        # list_apps.sort(key = lambda x:x['updated_on'], reverse=True)
        for app in list_apps:
            add_data = Apps.objects.get(id=app["app_id"])
            app["app_type"] = add_data.name
        data = {
            'data' : list_apps
        }
        print("LIST: ",data)
        return JsonResponse(data)