from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.models import AppInstance, Apps


class PublicAppsAPI(viewsets.ReadOnlyModelViewSet):
    """
    The Public Apps API with read-only methods to get public apps information.
    """

    queryset = (
        AppInstance.objects.filter(~Q(state="Deleted"), access="public")
        .order_by("-updated_on")[:8]
        .values("id", "name", "app_id", "table_field", "description", "updated_on")
    )

    def list(self, request):
        """
        This endpoint gets a list of public apps.
        :returns list: A list of app information.
        """
        print("PublicAppsAPI. Entered list method.")
        print(f"Requested API version {request.version}")

        list_apps = list(self.queryset)
        for app in list_apps:
            add_data = Apps.objects.get(id=app["app_id"])
            app["app_type"] = add_data.name
        data = {"data": list_apps}
        print("LIST: ", data)
        return JsonResponse(data)

    def retrieve(self, request, pk=None):
        """
        This endpoint retrieves a single public app instance.
        :returns dict: A dict of app information.
        """
        print(f"PublicAppsAPI. Entered retrieve method with pk = {pk}")
        print(f"Requested API version {self.request.version}")
        queryset = AppInstance.objects.all().values(
            "id", "name", "app_id", "table_field", "description", "updated_on", "access", "state"
        )
        app = get_object_or_404(queryset, pk=pk)
        if app["state"] == "Deleted":
            raise NotFound("this app has been deleted")
        if app["access"] != "public":
            raise NotFound()

        add_data = Apps.objects.get(id=app["app_id"])
        app["app_type"] = add_data.name
        data = {"app": app}
        return JsonResponse(data)


class AppsAPIView(generics.GenericAPIView):
    """
    The class for the Apps API.
    """

    def get(self, request):
        """
        This endpoint TODO
        """
        print(f"Requested API version {self.request.version}")
        message = "msg"
        if request.version == "v1":
            message = "This is API version 1."
        elif request.version == "v2":
            message = "This is API version 2."
        return Response({"message": message})

    def list(self, request):
        """
        This endpoint TODO
        """
        list_apps = []
        data = {"data": list_apps}
        print("LIST: ", data)
        return JsonResponse(data)

    def list_apps(self, request):
        """
        This endpoint TODO
        """
        list_apps = [{"name": "App Name"}]
        data = {"data": list_apps}
        print("LIST: ", data)
        return Response(data)