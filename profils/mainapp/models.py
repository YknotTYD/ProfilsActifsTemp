from django.contrib import admin
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.db.models.signals import post_delete
from django.dispatch import receiver
from . import constants

# TODO: constructors for models
# TODO: error messages

def strings_to_choice_char_fields(strings: tuple[str]) -> models.CharField:
    return models.CharField(
        max_length = max([len(i) for i in strings]),
        choices = [(r, r) for r in strings],
        default = strings[0]
    )

class Role(models.Model):

    user = models.ForeignKey(User, on_delete = models.CASCADE)
    role = strings_to_choice_char_fields(constants.ROLES)

    def __str__(self) -> str:
        return self.role

class VideoLink(models.Model):

    user = models.ForeignKey(User, on_delete = models.CASCADE)
    url  = models.CharField(max_length = 1024)

    def __str__(self):
        return f"VideoLink<{self.user};'{self.url}'>"

class VideoFile(models.Model):

    user = models.ForeignKey(User, on_delete = models.CASCADE)
    file = models.FileField(
        upload_to = 'videos/',
        validators = [FileExtensionValidator(allowed_extensions = ['mp4', 'mov', 'avi', 'webm'])]
    )

    def __str__(self):
        return f"VideoFile<{self.user}>"

@receiver(post_delete, sender = VideoFile)
def delete_videofile_on_delete(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save = False)

class Reaction(models.Model):

    user     = models.ForeignKey(User,  on_delete = models.CASCADE)
    video    = models.ForeignKey(VideoLink, on_delete = models.CASCADE)
    reaction = strings_to_choice_char_fields(constants.REACTIONS)

    def __str__(self) -> str:
        return f"{self.reaction} from {self.user} on vid{self.video.id}"

def get_likes(vid: VideoLink):
    return len(Reaction.objects.filter(video = vid, reaction = "like"))
def get_dislikes(vid: VideoLink):
    return len(Reaction.objects.filter(video = vid, reaction = "dislike"))

VideoLink.likes    = property(get_likes)
VideoLink.dislikes = property(get_dislikes)

admin.site.register(Role)
admin.site.register(VideoLink)
admin.site.register(VideoFile)
admin.site.register(Reaction)
