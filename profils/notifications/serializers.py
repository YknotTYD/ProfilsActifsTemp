
from . import types

def notification(n) -> dict:
    return {
        "id":         n.id,
        "type":       n.type,
        "label":      types.label_for(n.type),
        "payload":    n.payload,
        "url":        n.url,
        "read":       n.is_read,
        "created_at": n.created_at.isoformat(),
    }
