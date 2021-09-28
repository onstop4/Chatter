from __future__ import annotations
from enum import Enum
import random
import string
from typing import Union
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.core.validators import validate_unicode_slug
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    def create_user(self, username_field, email_field, password=None, **kwargs):
        email_field = self.normalize_email(email_field)
        user = self.model(username=username_field, email=email_field, **kwargs)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, username_field, email_field, password=None, **kwargs):
        kwargs.setdefault("is_superuser", True)

        return self.create_user(username_field, email_field, password, **kwargs)


class User(AbstractBaseUser, PermissionsMixin):
    objects = UserManager()

    username_validator = UnicodeUsernameValidator()

    username = models.CharField(
        _("username"),
        max_length=30,
        unique=True,
        help_text=_(
            "Required. 30 characters or fewer. Letters, digits and @/./+/-/_ only."
        ),
        validators=[username_validator],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )
    email = models.EmailField(_("email address"))
    is_active = models.BooleanField(_("active"), default=True)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["email"]


def generate_room_number():
    """
    Generates a room number composed of 10 digits.
    """
    return "".join(random.sample(string.digits, 10))


class RoomAccessStatus(Enum):
    """
    Represents different statuses indicating if a user can/cannot join a room and why.
    """

    ALLOWED = "allowed"

    NOT_FOUND = "not found"
    BAD_USERNAME = "bad username"
    CONFIRM_REQUIRED = "confirm required"
    NOT_INVITED = "not invited"
    BANNED = "banned"


class RoomManager(models.Manager):
    def get_access_status(
        self, room_number, user, username
    ) -> tuple[Union[Room, None], RoomAccessStatus]:
        """
        Attempts to find the specified room and determines if user is allowed to access
        it. Will return tuple containing the Room instance (or None) and a
        RoomAccessStatus instance.
        """
        try:
            room = self.prefetch_related("banned_users", "invited_users").get(
                number=room_number
            )
            if not user.is_authenticated:
                validate_unicode_slug(username)
            if (
                room.access_type == Room.AccessTypes.CONFIRMED
                and not user.is_authenticated
            ):
                return (room, RoomAccessStatus.CONFIRM_REQUIRED)
            if room.banned_users.filter(username=username).exists():
                return (room, RoomAccessStatus.BANNED)
            if (
                room.access_type == Room.AccessTypes.PRIVATE
                and not room.invited_users.filter(username=username).exists()
            ):
                return (room, RoomAccessStatus.NOT_INVITED)
        except Room.DoesNotExist:
            return (None, RoomAccessStatus.NOT_FOUND)
        except ValidationError:
            return (room, RoomAccessStatus.BAD_USERNAME)
        return (room, RoomAccessStatus.ALLOWED)


class Room(models.Model):
    objects = RoomManager()

    class AccessTypes(models.TextChoices):
        PUBLIC = "PUBLIC", _("Public")
        CONFIRMED = "CONFIRMED", _("Confirmed only")
        PRIVATE = "PRIVATE", _("Private")

    name = models.CharField(_("Room name"), max_length=200)
    number = models.CharField(_("Room number"), max_length=10, unique=True)
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="rooms_owned"
    )
    access_type = models.CharField(
        _("Access type"),
        max_length=20,
        default="PUBLIC",
        choices=AccessTypes.choices,
        help_text=_(
            "Public means that users can join even if they are not logged in. "
            "Confirmed means that only users who are logged in and confirmed can join. "
            "Private means that only logged in users who you have granted access "
            "to can join."
        ),
    )
    locked = models.BooleanField(
        _("Locked"), default=False, help_text=_("Prevents more users from joining.")
    )
    password = models.CharField(_("Password"), max_length=200, null=True)

    invited_users = models.ManyToManyField(User, related_name="invited_to")
    banned_users = models.ManyToManyField(User, related_name="banned_from")

    def save(self, *args, **kwargs):
        """
        Ensures that a random room number is generated.
        """
        while not self.number:
            number = generate_room_number()
            if not Room.objects.filter(number=number):
                self.number = number
        super().save(*args, **kwargs)
