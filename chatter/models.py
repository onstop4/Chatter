from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.contrib.auth.validators import UnicodeUsernameValidator
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
