"""Pages de messagerie : de simples formulaires, dans le style de
`mainapp` -- pas besoin d'une interface JavaScript pour lire et envoyer un
message.
"""

from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import redirect, render

from profils.profiles.models import ProfileVideo

from . import services
from .http import BadRequest, MessagingAccessDenied
from .models import Conversation

def _login_required(request):
    return None if request.user.is_authenticated else redirect("/login/")

def conversations_page(request):
    """Mes conversations : `/messages/`."""
    if response := _login_required(request):
        return response

    conversations = [
        {
            "id": conv.id,
            "other_username": conv.other_participant(request.user).username,
            "preview": (conv.last_message.body[:80] if conv.last_message
                       else "Aucun message pour le moment."),
        }
        for conv in services.conversations_for(request.user)
    ]
    return render(request, "messaging/conversations.html", {"conversations": conversations})

def start_conversation_view(request):
    """`POST /messages/start/` : demarre -- ou retrouve -- une conversation,
    depuis un profil ou une video (section 4). Une tentative refusee
    renvoie simplement vers la liste des conversations : le bouton n'est
    jamais affiche a qui n'a pas le droit de cliquer dessus, donc n'importe
    qui l'atteignant ici sans y avoir droit contourne deliberement
    l'interface.
    """
    if response := _login_required(request):
        return response
    if request.method != "POST":
        return redirect("/messages/")

    recipient = User.objects.filter(username = request.POST.get("recipient", "")).first()
    if recipient is None:
        return redirect("/messages/")

    context = None
    if video_id := request.POST.get("video"):
        context = ProfileVideo.objects.filter(pk = video_id).first()

    try:
        conversation = services.start_conversation(request.user, recipient, context = context)
    except (MessagingAccessDenied, BadRequest):
        return redirect("/messages/")

    return redirect(f"/messages/{conversation.pk}/")

def conversation_thread_page(request, pk):
    """Fil de conversation : `/messages/<id>/`. GET l'affiche, POST y ajoute
    un message (redirection ensuite, pour eviter un renvoi au rafraichissement).
    """
    if response := _login_required(request):
        return response

    conversation = Conversation.objects.filter(pk = pk).first()
    if conversation is None or not conversation.has_participant(request.user):
        raise Http404

    if request.method == "POST":
        try:
            services.send_message(conversation, request.user, request.POST.get("body", ""))
        except (MessagingAccessDenied, BadRequest):
            pass
        return redirect(f"/messages/{pk}/")

    return render(request, "messaging/thread.html", {
        "conversation": conversation,
        "other": conversation.other_participant(request.user),
        "messages_list": conversation.messages.select_related("sender"),
    })
