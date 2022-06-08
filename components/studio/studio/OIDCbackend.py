from mozilla_django_oidc.auth import OIDCAuthenticationBackend

class OIDCbackend(OIDCAuthenticationBackend):
    def get_username(self, claims):
        print('local')
        print(claims)
        return claims.get('preferred_username')
    
    def create_user(self, claims):
        user = super(OIDCbackend, self).create_user(claims)
        # user.first_name = claims.get('given_name', '')
        # user.last_name = claims.get('family_name', '')
        # user.username = claims.get('name','')
        # user.save()

        return user
    
    def verify_claims(self, claims):
        verified = super(OIDCbackend, self).verify_claims(claims)
        print("Country: ", claims.get('country', []), " CLAIMS: ",claims )
        if claims.get('country', []):
            is_swedish = 'SE' in claims.get('country', [])
        elif claims.get('schac_home_organization', []):
            is_swedish = False
        else:
            is_swedish = True
        return verified and is_swedish