"""Command argument specs shared by area modules (no journal imports)."""


class Command:
    def __init__(self, call, args, *, target=None, targets=None, creates=None, adapt=None, encode=None, decode=None, prepare=None):
        # call: "service.method" or a function(container, **args); args: name -> spec; target: (table, arg) of the
        # row an existing-record command changes; creates: table of a new row;
        # adapt: optional function reshaping mapped arguments for the service.
        # encode: optional function (adapter, values) -> values on the saving device, turning local ids hidden
        # in structured arguments into UUIDs; decode(adapter, values) does the reverse on the home, before adapt.
        # prepare: optional function (container, values) -> values on the home, for an argument only the home can
        # recompute (a preview token made of that device's local ids).
        self.call, self.args, self.target, self.creates, self.adapt, self.encode, self.decode = call, args, target, creates, adapt, encode, decode
        self.prepare = prepare
        # targets: (table, arg) of a selection (a list of UUIDs) a bulk command changes; the rows together are its base.
        self.targets = targets


TEXT, LONG, DATE, MONTH, AMOUNT, RATE, INT, FLAG = "text", "long", "date", "month", "amount", "rate", "int", "flag"
# BYTES: a small file (at most 40 KiB) carried as base64; JSON: structured data with no local ids left in it.
BYTES, JSON = "bytes", "json"


def ref(table):
    return "ref:" + table


def optional(spec):
    return "?" + spec


def choice(*values):
    return "choice:" + "|".join(values)


def listof(spec):
    """A list (at most 200) of single values, e.g. selected rows."""
    return ("list", spec)


def items(**fields):
    """A list (at most 50) of records with these fields, e.g. split lines."""
    return ("items", fields)


def mapping(**fields):
    """A record of named values, each optional (a service's `changes` dict); a key the spec lacks is refused."""
    return ("map", fields, True)


def filtered(**fields):
    """Like `mapping`, but keys the spec lacks are dropped (a raw form posted as a filter)."""
    return ("map", fields, False)
