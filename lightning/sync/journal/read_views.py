"""Journal report rendering never runs ordinary read-triggered mutations."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps


_reading = ContextVar('journal_confirmed_read', default=False)


@contextmanager
def confirmed_reads(db=None):
    token = _reading.set(True)
    try:
        if db is None:
            yield
        else:
            with db.nonmutating_view():
                yield
    finally:
        _reading.reset(token)


def install(container):
    for service, name in ((container.planning, 'match_payments'), (container.reevaluations, 'process_due')):
        original = getattr(service, name)
        if getattr(original, '_journal_view_guard', False):
            continue
        def guard(function):
            @wraps(function)
            def call(*args, **kwargs):
                if _reading.get():
                    return 0
                return function(*args, **kwargs)
            call._journal_view_guard = True
            return call
        setattr(service, name, guard(original))
