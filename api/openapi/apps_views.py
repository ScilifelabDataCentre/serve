from rest_framework import generics
from rest_framework.response import Response


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

    def list_apps(self, request):
        """
        This endpoint TODO
        """
        list_apps = [{"name": "App Name"}]
        data = {"data": list_apps}
        print("LIST: ", data)
        return Response(data)
