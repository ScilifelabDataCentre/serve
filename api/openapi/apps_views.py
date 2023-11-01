from django.db.models import Q
from django.http import JsonResponse
from rest_framework import generics
from rest_framework.response import Response

from apps.models import AppInstance, Apps


def get_apps_list(request):
    list_apps = []
    data = {"data": list_apps}
    print("LIST: ", data)
    return JsonResponse(data)


class PublicAppsAPI(generics.ListAPIView):
    """
    The class for the Apps API.
    """

    list_apps = [{"id": "001", "name": "App Name"}]

    def list(self, request):
        """
        This endpoint TODO
        """
        data = {"data": self.list_apps}
        print("LIST: ", data)
        return Response(data)

    def get_queryset(self):
        data = self.list_apps[0]
        return Response(data)


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
