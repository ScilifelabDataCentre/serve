from django.conf import settings
from django.utils.http import urlencode

def keycloak_logout(request, return_url = None):
  logout_url = settings.OIDC_OP_LOGOUT_ENDPOINT
  if return_url is None:
    return_url = settings.LOGOUT_REDIRECT_URL
  return_to_url = request.build_absolute_uri(return_url)
  return logout_url + '?' + urlencode({'redirect_uri': return_to_url, 'client_id': settings.OIDC_RP_CLIENT_ID})