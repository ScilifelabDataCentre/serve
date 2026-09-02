"""
Privileged users: a category above regular users and below Django admins.

A user is made privileged by ``UserProfile.is_privileged`` or the ``common.privileged_user``
permission (directly or via the "Privileged users" group). Django admins are a separate, higher
category: they are not privileged users, but they may do everything a privileged user can.

"""

from django.core.exceptions import ObjectDoesNotExist

PRIVILEGED_USER_PERM = "common.privileged_user"
PRIVILEGED_USERS_GROUP = "Privileged users"


def _has_privileged_profile(user) -> bool:
    """
    Whether the profile marks them as privileged. Not every user has a profile.
    """
    try:
        profile = user.userprofile
    except ObjectDoesNotExist:
        return False

    return bool(profile.is_privileged)


def is_privileged_user(user) -> bool:
    """
    Whether the user has been made a privileged user, regardless of project.
    """
    if user is None or not user.is_authenticated or user.is_superuser:
        return False

    return _has_privileged_profile(user) or bool(user.has_perm(PRIVILEGED_USER_PERM))


def has_privileged_access(user, project) -> bool:
    """
    Whether the user may use privileged rights in this project.
    """
    if user is None or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if project is None or not is_privileged_user(user):
        return False

    if project.owner_id == user.pk:
        return True

    if project.pk is None:
        return False

    return bool(project.privileged_users.filter(pk=user.pk).exists())
