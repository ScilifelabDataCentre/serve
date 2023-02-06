USER_FIELDS = ['username', 'email', 'country']


def allowed_region(country):
    return "SE" in country

def create_user(strategy, details, backend, user=None, *args, **kwargs):
    if user:
        return {'is_new': False}

    fields = dict((name, kwargs.get(name, details.get(name)))
                  for name in backend.setting('USER_FIELDS', USER_FIELDS))
    
    if not fields:
        return
    # check if user is in the allowed region (Currently only accounts associated with swedish universities allowed.)
    if not allowed_region(fields['country']):
        return
    # delete country from fields because it is not part of the user model. Just there to check region on first signup.
    del fields['country']
    print("Fields: ", strategy)
    return {
        'is_new': True,
        'user': strategy.create_user(**fields)
    }

def user_details(strategy, details, backend, user=None, *args, **kwargs):
    """Update user details using data from provider."""
    if not user:
        return

    changed = False  # flag to track changes

    # Default protected user fields (username, id, pk and email) can be ignored
    # by setting the SOCIAL_AUTH_NO_DEFAULT_PROTECTED_USER_FIELDS to True
    if strategy.setting("NO_DEFAULT_PROTECTED_USER_FIELDS") is True:
        protected = ()
    else:
        protected = (
            "username",
            "id",
            "pk",
            "email",
            "password",
            "is_active",
            "is_staff",
            "is_superuser",
        )

    protected = protected + tuple(strategy.setting("PROTECTED_USER_FIELDS", []))

    # Update user model attributes with the new data sent by the current
    # provider. Update on some attributes is disabled by default, for
    # example username and id fields. It's also possible to disable update
    # on fields defined in SOCIAL_AUTH_PROTECTED_USER_FIELDS.
    field_mapping = strategy.setting("USER_FIELD_MAPPING", {}, backend)
    for name, value in details.items():
        # Convert to existing user field if mapping exists
        name = field_mapping.get(name, name)
        if value is None or not hasattr(user, name) or name in protected:
            continue

        current_value = getattr(user, name, None)
        if current_value == value:
            continue

        immutable_fields = tuple(strategy.setting("IMMUTABLE_USER_FIELDS", []))
        if name in immutable_fields and current_value:
            continue

        changed = True
        setattr(user, name, value)
    #set attribute is_active to true for all social logins. 
    setattr(user, 'is_active', True)
    if changed:
        strategy.storage.user.changed(user)
