"""Small bounded admission budgets for unauthenticated pairing transport work."""
from collections import OrderedDict
import time


class PairingRequestLimits:
    def __init__(self, *, clock=time.monotonic, peers=128, per_peer=16, global_limit=64, window=10, concurrent=8):
        self.clock, self.max_peers, self.per_peer = clock, peers, per_peer
        self.global_limit, self.window, self.concurrent = global_limit, window, concurrent
        self.clients = OrderedDict()
        self.global_start, self.total, self.active = clock(), 0, 0

    def enter(self, peer):
        now = self.clock()
        if now-self.global_start >= self.window:
            self.global_start, self.total = now, 0
        if self.active >= self.concurrent or self.total >= self.global_limit:
            return False
        start, count = self.clients.pop(peer, (now, 0))
        if now-start >= self.window:
            start, count = now, 0
        self.clients[peer] = (start, count)
        while len(self.clients) > self.max_peers:
            self.clients.popitem(last=False)
        if count >= self.per_peer:
            return False
        self.clients[peer] = (start, count+1)
        self.total += 1
        self.active += 1
        return True

    def leave(self):
        self.active = max(0, self.active-1)
