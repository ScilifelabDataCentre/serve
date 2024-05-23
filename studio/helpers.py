from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.db import transaction

from common.models import EmailVerificationTable


def do_delete_account(user_id: int) -> bool:
    """
    Deletes a user account.
    Sets user.is_active = False and userprofile.deleted_on to now.
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


def do_pause_account(user_id: int) -> bool:
    """
    Sets a user account to pause (on hold).
    Sets user.is_active = False and deletes the user verification token if it exists.
    :param int user_id: The user id.
    :returns bool user_account_paused: Indicates whether the user account was paused.
    """
    user = User.objects.get(pk=user_id)
    email_verification_table = EmailVerificationTable.objects.filter(user_id=user_id).first()

    user_account_paused = False

    with transaction.atomic():
        user.is_active = False
        user.save(update_fields=["is_active"])

        if email_verification_table is not None:
            email_verification_table.delete()

        user_account_paused = True

    return user_account_paused
