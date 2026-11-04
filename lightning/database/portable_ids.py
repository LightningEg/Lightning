"""Read confirmed portable record identities without creating or changing them."""
from lightning.core.errors import ValidationError


def portable_ids(db, entities):
    """Map selected local ids to their journal UUIDs, or retain ids on ordinary profiles."""
    wanted = {(entity, int(value)) for entity, ids in entities.items() for value in ids}
    if not wanted or not db.has_table('journal_ids'):
        return {key: key[1] for key in wanted}
    names = sorted({entity for entity, _ in wanted})
    marks = ','.join('?' for _ in names)
    found = {(row['entity'], row['local_id']): row['uuid'] for row in db.all(
        f'SELECT entity,local_id,uuid FROM journal_ids WHERE entity IN ({marks})', tuple(names))}
    if not wanted <= found.keys():
        raise ValidationError('A record is not synchronized yet. Refresh and try again.')
    return {key: found[key] for key in wanted}
