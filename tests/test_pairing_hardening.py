"""4E/4G/4I: uncertain delivery, bounded claims and authenticated recovery."""
import asyncio
import json
import os
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from test_journal_finance import devices
from test_journal_pairing import PASSWORD, nearby, started, home_candidate
from lightning.runtime.journal_enrollment import NewJournalReplica
from lightning.sync.identity import load_or_create
from lightning.sync.journal.codec import JournalError, digest, seal, unpack
from lightning.sync.journal.pairing import request_pairing
from lightning.sync.journal.request_limits import PairingRequestLimits


def dropping(factory, kind, *, before=False):
    fired = False
    def create(*args, **kwargs):
        original = factory(*args, **kwargs)
        async def exchange(wire):
            nonlocal fired
            target = unpack(wire)["body"]["type"] == kind and not fired
            if target:
                fired = True
                if before:
                    raise TimeoutError("Injected before delivery")
            result = await original(wire)
            if target:
                raise TimeoutError("Injected lost reply")
            return result
        return exchange
    return create


@pytest.mark.parametrize("kind,before", [("journal-pairing-request",True),("journal-pairing-request",False),("journal-pairing-reveal",False)])
def test_handshake_resumes_identical_request_and_first_challenge(devices,kind,before):
    async def run():
        hs, make = nearby(devices)
        pc = make()
        await pc.find()
        normal = pc.client_factory
        pc.client_factory = dropping(normal,kind,before=before)
        with pytest.raises(TimeoutError):
            await pc.join(pc.screen()["nearby"][0]["id"])
        saved = pc._value("pairing_client")
        assert saved["stage"] == "handshake" and saved["wire"]
        first_challenge = saved.get("challenge")
        resumed = make()
        await resumed.resume()
        assert resumed.screen()["stage"] == "compare"
        assert resumed.screen()["pending"] == hs.screen()["digits"]
        assert hs._value("pairing")["attempts"] == 1
        if first_challenge:
            assert resumed._value("pairing_client")["challenge"] == first_challenge
        assert "secret" not in resumed._value("pairing_client")
    asyncio.run(run())


@pytest.mark.parametrize("home_first",[True,False])
def test_lost_password_reply_resumes_and_admits_exactly_once(devices,home_first):
    async def run():
        hs, make, pc = await started(devices)
        before = devices[0].store.fingerprint()
        pc.compare(pc.screen()["pending"])
        if home_first:
            hs.confirm(hs.screen()["digits"])
        pc.client_factory = dropping(pc.client_factory,"journal-pairing-proof")
        with pytest.raises(TimeoutError):
            await pc.prove(PASSWORD)
        saved = pc._value("pairing_client")
        assert saved["stage"] == "proving"
        assert not any(name in saved for name in ("password","verifier","proof"))
        resumed = make()
        await resumed.resume()
        assert resumed.screen()["stage"] == "waiting"
        if not home_first:
            hs.confirm(hs.screen()["digits"])
        await resumed.finish()
        assert hs.membership.state()["version"] == 2
        assert devices[0].store.fingerprint() == before
    asyncio.run(run())


def test_first_enrollment_recovers_lost_proof_reply_without_password_storage(devices,tmp_path):
    async def run():
        hs, _ = nearby(devices)
        candidate = home_candidate(hs)
        async def search(identity):
            return [candidate]
        def factory(endpoint,certificate,timeout):
            async def exchange(wire):
                return hs.enrollment.exchange(wire) if endpoint.endswith('/enrollment/exchange') else hs.exchange(wire)
            return exchange
        pc = NewJournalReplica(tmp_path/'new-native','New laptop',search=search,client_factory=factory)
        found = await pc.find()
        await pc.join(found[0]["id"])
        pc.compare(pc.state()["digits"])
        hs.confirm(hs.screen()["digits"])
        pc.client_factory = dropping(factory,"journal-pairing-proof")
        with pytest.raises(TimeoutError):
            await pc.prove(PASSWORD)
        assert pc.state()["stage"] == "proving"
        assert PASSWORD not in (pc.root/'enrollment.json').read_text()
        resumed = NewJournalReplica(pc.root,'New laptop',search=search,client_factory=factory)
        await resumed.resume()
        assert await resumed.finish(PASSWORD)
        assert hs.membership.state()["version"] == 2
    asyncio.run(run())


def test_changed_challenge_after_lost_reveal_cannot_create_another_number(devices):
    async def run():
        hs, make = nearby(devices)
        pc = make()
        await pc.find()
        pc.client_factory = dropping(pc.client_factory,"journal-pairing-reveal")
        with pytest.raises(TimeoutError):
            await pc.join(pc.screen()["nearby"][0]["id"])
        original = pc._value("pairing_client")["challenge"]
        def fake(endpoint,certificate,timeout):
            async def exchange(wire):
                body = unpack(wire)["body"]
                assert body["type"] == "journal-pairing-reveal" and body["challenge"] == original
                return seal(dict(type="pairing-matched",request=body["request"],challenge="0"*64,
                                 reveal=digest(body)),devices[0].identity.sign)
            return exchange
        pc.client_factory = fake
        with pytest.raises(JournalError,match="transcript"):
            await pc.resume()
        assert pc._value("pairing_client")["challenge"] == original
        assert pc.screen()["stage"] == "handshake"
    asyncio.run(run())


def test_recovery_response_requires_fresh_status_nonce(devices):
    async def run():
        hs, make, pc = await started(devices)
        pc.compare(pc.screen()["pending"])
        await pc.prove(PASSWORD)
        hs.confirm(hs.screen()["digits"])
        response = None
        normal = pc.client_factory
        def replay(endpoint,certificate,timeout):
            original = normal(endpoint,certificate,timeout)
            async def exchange(wire):
                nonlocal response
                if response is None:
                    response = await original(wire)
                return response
            return exchange
        pc.client_factory = replay
        state = pc._client_state()
        from lightning.sync.journal import pairing_client
        await pairing_client.status(state,pc.device.identity,pc._exchange(state),pc._save_client)
        with pytest.raises(JournalError,match="challenge"):
            await pairing_client.status(state,pc.device.identity,pc._exchange(state),pc._save_client)
    asyncio.run(run())


def test_cached_approval_rejects_revocation_and_uses_latest_membership(devices,tmp_path):
    async def run():
        hs, make, pc = await started(devices)
        pc.compare(pc.screen()["pending"])
        await pc.prove(PASSWORD)
        hs.confirm(hs.screen()["digits"])
        state = pc._client_state()
        other = load_or_create(tmp_path/'third','Third device')
        members = dict(hs.membership.state()["members"])
        members[other.device_id] = dict(key=other.public_key,incarnation=str(uuid4()))
        hs.membership.rotate(members)
        wire = seal(dict(type="journal-pairing-status",request=state["request"],device=pc.device.identity.device_id),pc.device.identity.sign)
        result = unpack(hs.exchange(wire))["body"]
        assert unpack(result["membership"].encode())["body"]["version"] == 3
        hs.revoke(pc.device.identity.device_id)
        with pytest.raises(JournalError,match="no longer"):
            hs.exchange(wire)
    asyncio.run(run())


def test_expired_receipt_blocks_status_and_enrollment(devices):
    async def run():
        hs, _, pc = await started(devices)
        pc.compare(pc.screen()["pending"])
        await pc.prove(PASSWORD)
        hs.confirm(hs.screen()["digits"])
        identifier = pc._client_state()["request"]
        saved = hs._value('pairing_result:'+identifier)
        saved['expires'] = int(time.time())-1
        hs._save('pairing_result:'+identifier,saved)
        status = seal(dict(type='journal-pairing-status',request=identifier,device=pc.device.identity.device_id),pc.device.identity.sign)
        with pytest.raises(JournalError,match='expired'):
            hs.exchange(status)
        config = pc.device.store.config
        query = dict(type='journal-enrollment',profile=config['profile'],generation=config['generation'],
                     sender=pc.device.identity.device_id,request=identifier,operation='metadata',index=0,nonce='1'*64)
        with pytest.raises(JournalError,match='expired'):
            hs.enrollment.exchange(seal(query,pc.device.identity.sign))
    asyncio.run(run())


def test_lease_releases_abandoned_claim_and_old_request_never_returns(devices,tmp_path):
    hs, _ = nearby(devices)
    now = int(time.time())
    hs.desk.clock = lambda: now
    hs.begin(PASSWORD)
    offer = hs._value('pairing')['offer'].encode()
    wire,_ = request_pairing(offer,'',devices[1].identity,str(uuid4()),home_key=devices[0].identity.public_key,secret=os.urandom(32))
    hs.exchange(wire)
    first = hs._value('pairing')
    now += 5
    hs.exchange(wire)
    assert hs._value('pairing')['lease'] == first['lease']
    now += 30
    other = load_or_create(tmp_path/'claimant','Another device')
    next_wire,_ = request_pairing(offer,'',other,str(uuid4()),home_key=devices[0].identity.public_key,secret=os.urandom(32))
    hs.exchange(next_wire)
    assert hs._value('pairing')['attempts'] == 2
    with pytest.raises(JournalError):
        hs.exchange(wire)
    assert not hs._value('pairing')['confirmed'] and not hs._value('pairing')['proof']


def test_malformed_unauthenticated_messages_do_not_burn_password_budget(devices):
    hs, _ = nearby(devices)
    for _ in range(10):
        with pytest.raises(JournalError):
            hs.exchange(b'{}')
    assert hs._value('pairing')['proof_attempts'] == 0
    assert hs._value('pairing')['attempts'] == 0


def test_cancellation_of_undelivered_request_is_safe_and_idempotent(devices):
    async def run():
        hs, make = nearby(devices)
        pc = make()
        await pc.find()
        pc.client_factory = dropping(pc.client_factory,'journal-pairing-request',before=True)
        with pytest.raises(TimeoutError):
            await pc.join(pc.screen()['nearby'][0]['id'])
        resumed = make()
        await resumed.cancel()
        assert resumed.screen()['pending'] is None
        assert hs._value('pairing')['request'] is None
    asyncio.run(run())


def test_rate_limits_bound_peers_concurrency_and_global_work():
    now = [0]
    limits = PairingRequestLimits(clock=lambda:now[0],peers=3,per_peer=2,global_limit=4,concurrent=1)
    assert limits.enter('one')
    assert not limits.enter('two')
    limits.leave()
    assert limits.enter('one'); limits.leave()
    assert not limits.enter('one')
    for peer in ('two','three'):
        assert limits.enter(peer); limits.leave()
    assert not limits.enter('four') and len(limits.clients) <= 3
    now[0] += 11
    assert limits.enter('four'); limits.leave()
    assert len(limits.clients) <= 3


def test_unapproved_password_guesses_never_exhaust_owner_cooldown(devices):
    async def run():
        hs, _, pc = await started(devices)
        pc.compare(pc.screen()['pending'])
        from lightning.sync.journal.pairing import prove_pairing
        state = pc._client_state()
        for _ in range(3):
            wire = prove_pairing(state['candidate']['offer'].encode(),state['wire'].encode(),
                                'hostile wrong password',pc.device.identity,home_key=state['home_key'])
            reply = unpack(hs.exchange(wire))['body']
            assert reply['type'] == 'pairing-wait'
        assert hs._value('pairing')['proof_attempts'] == 0
        assert not hs._value('pairing_abuse')
        hs.stop()
        hs.begin(PASSWORD)
        assert hs.screen()['code']
    asyncio.run(run())


def test_owner_rejection_of_queued_wrong_proof_returns_client_to_password(devices):
    async def run():
        hs, make, pc = await started(devices)
        pc.compare(pc.screen()['pending'])
        await pc.prove('wrong password')
        with pytest.raises(JournalError,match='password is wrong'):
            hs.confirm(hs.screen()['digits'])
        assert hs._value('pairing')['proof_attempts'] == 1
        with pytest.raises(JournalError,match='not available'):
            await pc.finish()
        assert pc.screen()['stage'] == 'password'
        await pc.prove(PASSWORD)
        await pc.finish()
    asyncio.run(run())


def test_cancellation_after_uncertain_proof_never_forgets_approved_identity(devices):
    async def run():
        hs, make, pc = await started(devices)
        pc.compare(pc.screen()['pending'])
        hs.confirm(hs.screen()['digits'])
        pc.client_factory = dropping(pc.client_factory,'journal-pairing-proof')
        with pytest.raises(TimeoutError):
            await pc.prove(PASSWORD)
        resumed = make()
        with pytest.raises(JournalError,match='already approved'):
            await resumed.cancel()
        assert resumed.screen()['stage'] == 'waiting'
        await resumed.finish()
        assert hs.membership.state()['version'] == 2
    asyncio.run(run())


def test_native_poll_resumes_uncertain_proof_and_keeps_password_hidden(devices):
    async def run():
        hs, make, pc = await started(devices)
        pc.compare(pc.screen()['pending'])
        hs.confirm(hs.screen()['digits'])
        pc.client_factory = dropping(pc.client_factory,'journal-pairing-proof')
        with pytest.raises(TimeoutError):
            await pc.prove(PASSWORD)
        from fastapi import FastAPI
        import httpx
        from lightning.runtime.journal_ui_routes import journal_ui_router
        session = SimpleNamespace(token='dummy-native-resume',container=None,
                                  journal=SimpleNamespace(device=devices[1],pairing=make(),trust=None))
        app = FastAPI(); app.include_router(journal_ui_router(session))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            before = await client.get('/journal/devices')
            assert 'Resume pairing' in before.text and 'name="password"' not in before.text
            response = await client.post('/journal/devices/poll',data={'__session':session.token})
            assert response.status_code == 200 and 'version' in response.json()
            assert session.journal.pairing.screen()['stage'] == 'waiting'
    asyncio.run(run())


def test_protocol_gate_refuses_oversized_body_before_profile_mutex():
    async def run():
        from lightning.runtime.journal_profile import _ProtocolGate
        entered = []
        class Mutex:
            async def __aenter__(self): entered.append(True)
            async def __aexit__(self,*args): pass
        async def app(scope,receive,send):
            raise AssertionError('Refused body reached app')
        gate = _ProtocolGate(app,SimpleNamespace(gate=SimpleNamespace(mutex=Mutex()),closed=False))
        scope = dict(type='http',path='/pairing/exchange',method='POST',headers=[(b'content-length',b'5000')],client=('127.0.0.1',1))
        messages = []
        async def receive():
            raise AssertionError('Oversized advertised body was read')
        async def send(message): messages.append(message)
        await gate(scope,receive,send)
        assert messages[0]['status'] == 413 and not entered
        assert gate.pairing_limits.active == 0
    asyncio.run(run())


def test_protocol_gate_hard_deadline_rejects_slow_peer_without_mutex(monkeypatch):
    async def run():
        from lightning.runtime.journal_profile import _ProtocolGate
        entered = []
        class Mutex:
            async def __aenter__(self): entered.append(True)
            async def __aexit__(self,*args): pass
        async def app(scope,receive,send): raise AssertionError('Slow peer reached app')
        gate = _ProtocolGate(app,SimpleNamespace(gate=SimpleNamespace(mutex=Mutex()),closed=False))
        async def expire(coroutine,timeout):
            assert timeout == 3
            coroutine.close()
            raise TimeoutError
        monkeypatch.setattr(asyncio,'wait_for',expire)
        scope = dict(type='http',path='/pairing/exchange',method='POST',headers=[],client=('127.0.0.1',1))
        messages = []
        async def receive(): return dict(type='http.request',body=b'',more_body=True)
        async def send(message): messages.append(message)
        await gate(scope,receive,send)
        assert messages[0]['status'] == 408 and not entered
        assert gate.pairing_limits.active == 0
    asyncio.run(run())


def test_cancel_can_clear_revoked_identity_after_receipt_expiry(devices):
    async def run():
        hs, _, pc = await started(devices)
        pc.compare(pc.screen()['pending'])
        await pc.prove(PASSWORD)
        hs.confirm(hs.screen()['digits'])
        identifier = pc._client_state()['request']
        saved = hs._value('pairing_result:'+identifier)
        saved['expires'] = int(time.time())-1
        hs._save('pairing_result:'+identifier,saved)
        with pytest.raises(JournalError,match='already approved'):
            await pc.cancel()
        hs.revoke(pc.device.identity.device_id)
        await pc.cancel()
        assert pc.screen()['pending'] is None
    asyncio.run(run())


@pytest.mark.parametrize('field,value', [('original',[]),('original',1),('offer_wire',{}),('offer_wire',None),('original','{}')])
def test_malformed_extended_cancel_is_controlled_refusal(devices,field,value):
    async def run():
        hs, _, pc = await started(devices)
        state = pc._client_state()
        offer = unpack(state['candidate']['offer'].encode())['body']
        body = dict(type='journal-pairing-cancel',offer=digest(offer),request=state['request'],
                    device=pc.device.identity.device_id,original=state['wire'],offer_wire=state['candidate']['offer'])
        body[field] = value
        with pytest.raises(JournalError):
            hs.exchange(seal(body,pc.device.identity.sign))
        assert hs._value('pairing')['request'] == state['wire']
        assert hs._value('pairing')['proof_attempts'] == 0
    asyncio.run(run())
