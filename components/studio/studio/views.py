from django.conf import settings
from django.contrib.auth.models import User
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.shortcuts import render
from django.http import HttpResponseRedirect
from rest_framework.authentication import (BasicAuthentication,
                                           SessionAuthentication,
                                           TokenAuthentication)
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.models import AppInstance
from projects.models import Project


@receiver(pre_save, sender=User)
def set_new_user_inactive(sender, instance, **kwargs):
    if instance._state.adding is True and settings.INACTIVE_USERS:
        print("Creating Inactive User")
        instance.is_active = False
    else:
        print("Updating User Record")

def home(request):
    menu = dict()
    menu['home'] = 'active'
    base_template = 'base.html'
    if 'project' in request.session:
        project_slug = request.session['project']
        is_authorized = kc.keycloak_verify_user_role(request, project_slug, ['member'])
        if is_authorized:
            try:
                project = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status='active', slug=project_slug).first()
                base_template = 'baseproject.html'
            except Exception as err:
                project = []
                print(err)
            if not project:
                base_template = 'base.html'
    template = 'home.html'
    return render(request, template, locals())


def contact(request):
    menu = dict()
    menu['contact'] = 'active'
    base_template = 'base.html'
    if 'project' in request.session:
        project_slug = request.session['project']
        is_authorized = kc.keycloak_verify_user_role(request, project_slug, ['member'])
        if is_authorized:
            try:
                project = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status='active', slug=project_slug).first()
                base_template = 'baseproject.html'
            except Exception as err:
                project = []
                print(err)
            if not project:
                base_template = 'base.html'
    return render(request, 'contact.html', locals())


def about(request):
    menu = dict()
    menu['about'] = 'active'
    base_template = 'base.html'
    if 'project' in request.session:
        project_slug = request.session['project']
        is_authorized = kc.keycloak_verify_user_role(request, project_slug, ['member'])
        if is_authorized:
            try:
                project = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status='active', slug=project_slug).first()
                base_template = 'baseproject.html'
            except Exception as err:
                project = []
                print(err)
            if not project:
                base_template = 'base.html'
    return render(request, 'about.html', locals())


def teaching(request):
    menu = dict()
    menu['teaching'] = 'active'
    base_template = 'base.html'
    if 'project' in request.session:
        project_slug = request.session['project']
        is_authorized = kc.keycloak_verify_user_role(request, project_slug, ['member'])
        if is_authorized:
            try:
                project = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status='active', slug=project_slug).first()
                base_template = 'baseproject.html'
            except Exception as err:
                project = []
                print(err)
            if not project:
                base_template = 'base.html'
    return render(request, 'teaching.html', locals())


def guide(request):
    menu = dict()
    menu['guide'] = 'active'
    base_template = 'base.html'
    if 'project' in request.session:
        project_slug = request.session['project']
        is_authorized = kc.keycloak_verify_user_role(request, project_slug, ['member'])
        if is_authorized:
            try:
                project = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status='active', slug=project_slug).first()
                base_template = 'baseproject.html'
            except Exception as err:
                project = []
                print(err)
            if not project:
                base_template = 'base.html'
    template = 'user_guide.html'
    return render(request, template , locals())


def dash_docker(request):
    menu = dict()
    menu['guide'] = 'active'
    base_template = 'base.html'
    if 'project' in request.session:
        project_slug = request.session['project']
        is_authorized = kc.keycloak_verify_user_role(request, project_slug, ['member'])
        if is_authorized:
            try:
                project = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status='active', slug=project_slug).first()
                base_template = 'baseproject.html'
            except Exception as err:
                project = []
                print(err)
            if not project:
                base_template = 'base.html'
    template = 'guide_dash_docker.html'
    return render(request, template , locals())


def shiny_docker(request):
    menu = dict()
    menu['guide'] = 'active'
    base_template = 'base.html'
    if 'project' in request.session:
        project_slug = request.session['project']
        is_authorized = kc.keycloak_verify_user_role(request, project_slug, ['member'])
        if is_authorized:
            try:
                project = Project.objects.filter(Q(owner=request.user) | Q(authorized=request.user), status='active', slug=project_slug).first()
                base_template = 'baseproject.html'
            except Exception as err:
                project = []
                print(err)
            if not project:
                base_template = 'base.html'
    template = 'guide_shiny_docker.html'
    return render(request, template , locals())

# Since this is a production feature, it will only work if DEBUG is set to False


def handle_page_not_found(request, exception):
    return HttpResponseRedirect('/')


class AccessPermission(BasePermission):

    def has_permission(self, request, view):
        """
        Should simply return, or raise a 403 response.
        """
        try:
            release = request.GET.get('release')
            app_instance = AppInstance.objects.get(
                parameters__contains={'release': release})
            project = app_instance.project
        except:
            project_slug = request.GET.get('project')
            project = Project.objects.get(slug=project_slug)
            return request.user.has_perm('can_view_project', project)

        if app_instance.access == "private":
            return app_instance.owner == request.user
        elif app_instance.access == "project":
            return request.user.has_perm('can_view_project', project)
        else:
            return True


class ModifiedSessionAuthentication(SessionAuthentication):
    """
    This class is needed, because REST Framework's default SessionAuthentication does never return 401's,
    because they cannot fill the WWW-Authenticate header with a valid value in the 401 response. As a
    result, we cannot distinguish calls that are not unauthorized (401 unauthorized) and calls for which
    the user does not have permission (403 forbidden). See https://github.com/encode/django-rest-framework/issues/5968

    We do set authenticate_header function in SessionAuthentication, so that a value for the WWW-Authenticate
    header can be retrieved and the response code is automatically set to 401 in case of unauthenticated requests.
    """

    def authenticate_header(self, request):
        return 'Session'


class AuthView(APIView):
    authentication_classes = [
        ModifiedSessionAuthentication, TokenAuthentication]
    permission_classes = [IsAuthenticated, AccessPermission]

    def get(self, request, format=None):
        content = {
            'user': str(request.user),
            'auth': str(request.auth),
        }
        return Response(content)
