from django.contrib import admin
from django.core.exceptions import ValidationError
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

    user       = models.ForeignKey(User, on_delete = models.CASCADE)
    role       = strings_to_choice_char_fields(constants.ROLES)
    birth_date = models.DateField(null = True, blank = True)

    def __str__(self) -> str:
        return self.role

class VideoLink(models.Model):
    """Video de presentation soumise par lien (feed recruteur/admin).

    Aucune video ici n'est visible avant moderation : `status` demarre a
    "PENDING" et seul "APPROVED" est repris par le feed (voir `views.
    get_videos`). Le motif est obligatoire pour un refus, verifie par
    `clean()` -- appele par le formulaire d'administration a chaque
    changement de statut.
    """

    user = models.ForeignKey(User, on_delete = models.CASCADE)
    url  = models.CharField(max_length = 1024)

    status = strings_to_choice_char_fields(constants.VIDEO_LINK_STATUSES)
    rejection_reason = models.TextField(blank = True, default = "")

    def __str__(self):
        return f"VideoLink<{self.user};'{self.url}'>"

    def clean(self):
        super().clean()
        if self.status == constants.VIDEO_LINK_REJECTED and not self.rejection_reason.strip():
            raise ValidationError({
                "rejection_reason": "un motif est obligatoire pour refuser une video.",
            })

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

@admin.register(VideoLink)
class VideoLinkAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "url", "status")
    list_filter  = ("status",)
    search_fields = ("user__username", "url")


admin.site.register(Role)
admin.site.register(Reaction)
