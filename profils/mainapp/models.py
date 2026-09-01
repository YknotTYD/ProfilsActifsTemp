from django.contrib import admin
from django.db import models
from django.contrib.auth.models import User
from . import constants

class Role(models.Model):

    user = models.OneToOneField(User, on_delete = models.CASCADE)
    role = models.CharField(
        max_length = max([len(i) for i in constants.ROLES]),
        choices = [(r, r) for r in constants.ROLES],
        default = constants.ROLES[0]
    )

    def __str__(self):
        return self.role

class Video(models.Model):

    user = models.OneToOneField(User, on_delete = models.CASCADE)
    url  = models.CharField(max_length = 1024)

    def __str__(self):
        return f"Video<{self.user};'{self.url}'>"

admin.site.register(Role)
admin.site.register(Video)
