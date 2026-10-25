import hashlib
import json
from datetime import timedelta, timezone
from uuid import uuid4
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from .models import AuditLog, AuditChainHead, utcnow


def audit(db, user, action, entity_id, institution_id=None, before=None, after=None):
    db.flush()
    # A single locked head serialises concurrent writers for the same entity.
    if db.get_bind().dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    db.execute(insert(AuditChainHead).values(entity_id=str(entity_id), event_hash='')
               .on_conflict_do_nothing(index_elements=['entity_id']))
    head = db.scalar(select(AuditChainHead).where(AuditChainHead.entity_id == str(entity_id))
                     .with_for_update().execution_options(populate_existing=True))
    created_at = utcnow()
    if head.last_created_at and created_at <= head.last_created_at.replace(tzinfo=timezone.utc):
        created_at = head.last_created_at.replace(tzinfo=timezone.utc) + timedelta(microseconds=1)
    entry = AuditLog(id=str(uuid4()), created_at=created_at, actor_id=user.id if user else None,
                     institution_id=institution_id, entity_id=str(entity_id), action=action,
                     before=jsonable_encoder(before or {}), after=jsonable_encoder(after or {}),
                     previous_hash=head.event_hash)
    entry.event_hash = event_digest(entry)
    head.event_hash, head.last_created_at = entry.event_hash, created_at
    db.add(entry)
    db.flush()
    return entry


def event_digest(entry):
    payload = {"id": entry.id, "actor_id": entry.actor_id, "entity_id": entry.entity_id, "institution_id": entry.institution_id,
               "action": entry.action, "before": entry.before, "after": entry.after, "previous_hash": entry.previous_hash,
               "created_at": entry.created_at.replace(tzinfo=None).isoformat()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
