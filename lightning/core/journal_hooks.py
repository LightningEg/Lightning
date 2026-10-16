"""Optional action recording for module-level financial workflows.

Ordinary execution has no recorder. Consumers supply an owning-context recorder;
this module knows nothing about journal storage, transport, or replication.
"""
from contextvars import ContextVar
from functools import wraps
import inspect


recorder = ContextVar('financial_action_recorder', default=None)


def named_action(name):
    def decorate(function):
        signature = inspect.signature(function)
        receiver_name = next(iter(signature.parameters))

        @wraps(function)
        def call(*args, **kwargs):
            current = recorder.get()
            if current is None:
                return function(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            receiver = bound.arguments[receiver_name]
            arguments = {key: value for key, value in bound.arguments.items() if key != receiver_name}
            return current.named(name, receiver, arguments, lambda: function(*args, **kwargs))
        return call
    return decorate
