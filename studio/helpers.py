from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.db import transaction


def do_delete_account(user_id):
    """
    Sets user.is_active = False and userprofile.deleted_on to now.
    Also sends an email to the user email adress on record.
    :param int user_id: The user id.
    :returns bool user_account_deleted: Indicates whether the user account was deleted.
    """
    user = User.objects.get(pk=user_id)

    user_account_deleted = False

    with transaction.atomic():
        user.is_active = False
        user.userprofile.deleted_on = datetime.now(timezone.utc)

        user.save(update_fields=["is_active"])
        user.userprofile.save(update_fields=["deleted_on"])

        user_account_deleted = True

    return user_account_deleted
