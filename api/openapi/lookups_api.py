import json

from django.conf import settings
from django.http import JsonResponse
from rest_framework import viewsets
from rest_framework.exceptions import (
    APIException,
    MethodNotAllowed,
    NotFound,
    ValidationError,
)


class UniversityLookupAPI(viewsets.GenericViewSet):
    """
    The university lookup API with read-only methods to get university information.
    """

    def __get_universities(self):
        """Get the universities data from the json file."""
        with open(settings.STATICFILES_DIRS[0] + "/common/universities.json", "r") as f:
            universities = json.load(f).get("universities", dict())
            list = [{"code": k, "name": v} for k, v in universities.items()]
            return list

    def list_or_single(self, request):
        """
        This method handles the /universities endpoint.
        With a query string get parameter "code" it returns a single university.
        Without a query string parameter it returns the entire list.

        :returns list of dict or dict: The dict contains attributes code and name.
        """
        print("UniversityLookupAPI. Entered list_or_single")

        try:
            universities = self.__get_universities()
        except Exception as e:
            print(f"Exception: {e}")
            raise APIException("Server error. Unable to retrieve list of universities from json file.")

        if len(request.GET) >= 1:
            if request.GET.get("code") is not None:
                # Get a single university item by code
                code = request.GET.get("code").lower()

                # Validate the user input string
                if not code.isalpha() or len(code) > 10:
                    raise ValidationError("Invalid input parameter code")

                item = next((item for item in universities if item["code"] == code), None)

                if item is None:
                    raise NotFound("No university found for the requersted code.")

                data = {"data": item}
                return JsonResponse(data)

            else:
                # Invalid query string get parameter passed in
                raise MethodNotAllowed(
                    "/universities",
                    detail="MethodNotAllowed. Invalid endpoint. The query string get parameter is not supported.",
                )

        else:
            # Get all universities
            data = {"data": universities}
            return JsonResponse(data)


class DepartmentLookupAPI(viewsets.GenericViewSet):
    """
    The department lookup API with read-only methods to get departments.
    """

    def __get_departments(self):
        """Get the departments data from the json file."""
        with open(settings.STATICFILES_DIRS[0] + "/common/departments.json", "r") as f:
            departments = json.load(f).get("departments", [])
            return departments

    def list(self, request):
        """Gets a list of departments."""
        print("DepartmentLookupAPI. Entered list")

        try:
            departments = self.__get_departments()
        except Exception as e:
            print(f"Exception: {e}")
            raise APIException("Server error. Unable to retrieve list of departments from json file.")

        data = {"data": departments}
        return JsonResponse(data)
