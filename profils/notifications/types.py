##types.py
"""Registre des types de notification (spec section 5).

Un simple dictionnaire plutot qu'un `choices=` sur le modele : ajouter un
type -- "candidature reçue", demain -- est une ligne ici, jamais une
migration. `notify()` (dans `services.py`) est le seul point qui verifie
qu'un code existe dans ce registre avant d'ecrire quoi que ce soit.
"""

VIDEO_APPROVED  = "VIDEO_APPROVED"
VIDEO_REJECTED  = "VIDEO_REJECTED"
VIDEO_HIDDEN    = "VIDEO_HIDDEN"
NEW_MESSAGE     = "NEW_MESSAGE"
VIDEO_LIKED     = "VIDEO_LIKED"
VIDEO_DISLIKED  = "VIDEO_DISLIKED"

#: code -> libellé affiché. Le sens humain du type ; le comportement (email,
#: push...) viendra se greffer ici plus tard sans toucher au modèle.
LABELS = {
    VIDEO_APPROVED: "Votre vidéo a été validée",
    VIDEO_REJECTED: "Votre vidéo a été refusée",
    VIDEO_HIDDEN:   "Un changement important concerne une de vos vidéos",
    NEW_MESSAGE:    "Nouveau message",
    VIDEO_LIKED:    "Votre vidéo a reçu un like",
    VIDEO_DISLIKED: "Votre vidéo a reçu un dislike",
}


def is_known(type_code: str) -> bool:
    return type_code in LABELS


def label_for(type_code: str) -> str:
    return LABELS.get(type_code, type_code)
