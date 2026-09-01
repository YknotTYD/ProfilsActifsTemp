from django.contrib import admin
from django.db import models
from django.contrib.auth.models import User
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
    file = None

    def __str__(self):
        return f"VideoFile<{self.user}>"


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
admin.site.register(Reaction)
