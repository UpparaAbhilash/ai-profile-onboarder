"""Custom user model: users log in with their email address."""
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Creates users and superusers identified by email instead of username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        # If password is None, Django stores an "unusable" password.
        # We use this for auto-created accounts: the candidate sets their
        # own password through a secure one-time link (Phase 7).
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Application user. The email address is the unique login identifier."""

    username = None  # remove the username field inherited from AbstractUser
    email = models.EmailField("email address", unique=True)

    USERNAME_FIELD = "email"  # field used to log in
    REQUIRED_FIELDS = []      # extra fields asked for by createsuperuser

    objects = UserManager()

    def __str__(self) -> str:
        return self.email