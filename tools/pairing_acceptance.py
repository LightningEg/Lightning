"""Run the pairing failure matrix against NEW dummy profiles only.

    python tools/pairing_acceptance.py --dummy --root /path/to/empty/folder

Each case runs in separate Python processes before and after interrupted
network delivery. JSON distinguishes automated process evidence, native key
provider evidence and physical checks which remain unrun. No host networking,
firewall, production profile or Android settings are changed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

PASSWORD = "pairing acceptance dummy password"
CASES = ("request-before-delivery", "request-lost-reply", "reveal-lost-reply", "proof-lost-reply", "status-lost-reply")
PHYSICAL = {
    "same-wifi": "Both awake on the same Wi-Fi: discover names, select number, enter PC password, approve home, reconnect without another prompt.",
    "phone-hotspot": "Repeat on the phone hotspot. A blocked broadcast must leave a clear unavailable state and preserve the saved attempt.",
    "guest-isolation": "Repeat on guest/client-isolated Wi-Fi: refusal/unavailability is expected; do not weaken identity checks.",
    "windows-firewall": "Manually deny then allow the review app on a private network: no financial data changes while unavailable; retry resumes after access returns.",
    "address-change": "Switch Wi-Fi/change IP: rediscover and reconnect using the pinned identity. A different certificate must fail.",
    "android-sleep": "Screen off/Doze then reopen the phone: saved state survives and resumes; no claim of an always-running background listener.",
    "force-stop-reboot": "Force-stop/relaunch and reboot each device during request, reveal, proof and download: pairing reconciles or expires explicitly, without another writable home.",
    "interrupted-enrollment": "Interrupt download and reopen: verified chunks resume and the final financial fingerprint matches the home.",
}


def _write(path, data):
    with path.open("x",encoding="utf-8") as handle:
        json.dump(data,handle,indent=2)
        handle.write("\n")


def _worker(folder, case, phase):
    from lightning.runtime.journal_lab import open_lab
    from lightning.runtime.journal_pairing import NearbyPairing
    from lightning.runtime.session import read_slot
    from lightning.sync.journal.codec import unpack
    from lightning.sync.journal.membership import Membership
    if read_slot(folder/'acceptance-dummy.json') != dict(format=1,dummy=True):
        raise ValueError("Not an acceptance dummy directory")
    peers, _ = open_lab(folder,PASSWORD)
    home, pc = peers
    try:
        if not home.store.db.scalar("SELECT value FROM journal_local WHERE name='membership'"):
            members = {home.identity.device_id:dict(key=home.identity.public_key,incarnation=home.store.config['incarnation'])}
            Membership(home).initialize(members,os.urandom(32))
            Membership(pc).initialize(members,os.urandom(32))
            home.store.db.execute("DELETE FROM journal_origins WHERE device=?",(pc.identity.device_id,))
        hs = NearbyPairing(home,key_document=lambda:read_slot(folder/'keys.json'))
        if phase == 'interrupt':
            hs.begin(PASSWORD)
        async def search(identity):
            return [unpack(hs.advertise('0'*64,47513))['body'] | dict(endpoint='https://127.0.0.1:47513/pairing/exchange')]
        dropped = False
        def factory(endpoint,certificate,timeout):
            async def exchange(wire):
                nonlocal dropped
                kind = unpack(wire)['body']['type']
                target = {'request-before-delivery':'journal-pairing-request','request-lost-reply':'journal-pairing-request',
                          'reveal-lost-reply':'journal-pairing-reveal','proof-lost-reply':'journal-pairing-proof',
                          'status-lost-reply':'journal-pairing-status'}[case]
                fail = phase == 'interrupt' and kind == target and not dropped
                if fail:
                    dropped = True
                    if case == 'request-before-delivery':
                        os._exit(75)  # Deliberate process death after the documented durable boundary.
                answer = hs.exchange(wire)
                if fail:
                    os._exit(75)  # Deliberate process death after the documented durable boundary.
                return answer
            return exchange
        joining = NearbyPairing(pc,search=search,client_factory=factory)
        async def run():
            if phase == 'interrupt':
                await joining.find()
                try:
                    await joining.join(joining.screen()['nearby'][0]['id'])
                    joining.compare(joining.screen()['pending'])
                    hs.confirm(hs.screen()['digits'])
                    await joining.prove(PASSWORD)
                    await joining.finish()
                except TimeoutError:
                    pass
                if not dropped:
                    raise AssertionError('Fault was not exercised')
                return
            await joining.resume()
            stage = joining.screen()['stage']
            if stage == 'compare':
                joining.compare(joining.screen()['pending'])
            if joining.screen()['stage'] == 'password':
                hs.confirm(hs.screen()['digits'])
                await joining.prove(PASSWORD)
            await joining.finish()
            if Membership(home).state()['version'] != 2 or len(Membership(home).state()['members']) != 2:
                raise AssertionError('Membership changed more than once')
            if home.store.fingerprint() != pc.store.fingerprint():
                raise AssertionError('Financial copies differ')
        asyncio.run(run())
    finally:
        for peer in peers:
            if peer.store.authority:
                peer.store.authority.close()
            peer.c.db.close()


def _network_checks(folder):
    """Real loopback TLS and UDP; separate from physical-network claims."""
    import ssl
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import Response
    from lightning.runtime.journal_lab import LabServer, open_lab
    from lightning.runtime.journal_pairing import NearbyPairing
    from lightning.runtime.session import read_slot
    from lightning.sync.identity import load_or_create
    from lightning.sync.journal.codec import unpack
    from lightning.sync.journal.discovery import LanResponder, nearby_devices
    from lightning.sync.journal.local import LocalChannel, PinnedLocalClient
    from lightning.sync.journal.membership import Membership
    folder.mkdir(mode=0o700)
    peers, _ = open_lab(folder,PASSWORD)
    home, pc = peers
    members = {home.identity.device_id:dict(key=home.identity.public_key,incarnation=home.store.config['incarnation'])}
    Membership(home).initialize(members,os.urandom(32))
    Membership(pc).initialize(members,os.urandom(32))
    home.store.db.execute("DELETE FROM journal_origins WHERE device=?",(pc.identity.device_id,))
    hs = NearbyPairing(home,key_document=lambda:read_slot(folder/'keys.json'))
    results = []
    progress = ["listener"]
    async def exercise():
        app = FastAPI()
        @app.post('/pairing/exchange')
        async def exchange(request: Request):
            return Response(hs.exchange(await request.body()),media_type='application/octet-stream')
        config = home.identity.configure_uvicorn_tls(uvicorn.Config(app,host='127.0.0.1',port=0,access_log=False,log_level='error'))
        server = LabServer(config)
        task = asyncio.create_task(server.serve())
        udp = None
        try:
            for _ in range(200):
                if server.started:
                    break
                await asyncio.sleep(.025)
            if not server.started:
                raise RuntimeError('Loopback listener unavailable')
            port = server.servers[0].sockets[0].getsockname()[1]
            channel = LocalChannel(home,transport_key=bytes.fromhex(home.store.db.scalar("SELECT value FROM journal_local WHERE name='transport'")),peers={})
            responder = LanResponder(channel,tls_port=port,nearby=hs.advertise)
            udp,_ = await asyncio.get_running_loop().create_datagram_endpoint(lambda:responder,local_addr=('127.0.0.1',0))
            udp_port = udp.get_extra_info('sockname')[1]
            hs.begin(PASSWORD)
            found = await nearby_devices(pc.identity,port=udp_port,timeout=.1,destinations=('127.0.0.1',))
            if len(found) != 1:
                raise AssertionError('Open home not discovered')
            responder.port = port+1 if port<65535 else port-1
            changed = await nearby_devices(pc.identity,port=udp_port,timeout=.1,destinations=('127.0.0.1',))
            if changed[0]['endpoint'] == found[0]['endpoint']:
                raise AssertionError('Discovery hint was not refreshed')
            responder.port = port
            hs.stop()
            if await nearby_devices(pc.identity,port=udp_port,timeout=.1,destinations=('127.0.0.1',)):
                raise AssertionError('Closed pairing remained advertised')
            results.append(dict(case='discovery-open-stop-and-endpoint-change',result='passed',evidence='automated-loopback'))
            hs.begin(PASSWORD)
            candidate = unpack(hs.advertise('0'*64,port))['body'] | dict(endpoint=f'https://127.0.0.1:{port}/pairing/exchange')
            wrong = load_or_create(folder/'untrusted-certificate','Untrusted dummy')
            rejected = False
            try:
                await PinnedLocalClient(candidate['endpoint'],wrong.cert_path.read_text(),timeout=2)(b'{}')
            except (ssl.SSLError,OSError,ValueError):
                rejected = True
            if not rejected:
                raise AssertionError('Certificate substitution was accepted')
            results.append(dict(case='tls-certificate-substitution',result='passed',evidence='automated-loopback'))
            async def search(identity): return [candidate]
            joining = NearbyPairing(pc,search=search)
            progress[0] = "find"
            await joining.find()
            progress[0] = "join"
            await joining.join(joining.screen()['nearby'][0]['id'])
            progress[0] = "compare"
            joining.compare(joining.screen()['pending'])
            progress[0] = "approve"
            hs.confirm(hs.screen()['digits'])
            progress[0] = "prove"
            await joining.prove(PASSWORD)
            progress[0] = "finish"
            await joining.finish()
            progress[0] = "fingerprint"
            if Membership(home).state()['version'] != 2 or home.store.fingerprint()!=pc.store.fingerprint():
                raise AssertionError('TLS pairing did not preserve state')
            results.append(dict(case='pinned-tls-pairing',result='passed',evidence='automated-loopback'))
        finally:
            if udp: udp.close()
            server.should_exit = True
            await task
    try:
        asyncio.run(exercise())
    except Exception as error:
        results.append(dict(case='loopback-network',result='failed',evidence='automated-loopback',phase=progress[0],error=type(error).__name__))
    finally:
        for peer in peers:
            peer.c.db.close()
    return results


def run(folder):
    if folder.is_symlink() or folder.exists() and any(folder.iterdir()):
        raise ValueError('Choose an empty, non-symlink dummy directory')
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    results = []
    for case in CASES:
        destination = folder/case
        destination.mkdir(mode=0o700)
        # open_lab accepts only an empty root, so create its supported dummy
        # identity first, then mark the subprocess-only acceptance boundary.
        from lightning.runtime.journal_lab import open_lab
        peers,_ = open_lab(destination,PASSWORD)
        for peer in peers:
            peer.c.db.close()
        _write(destination/'acceptance-dummy.json',dict(format=1,dummy=True))
        successful = True
        for phase in ('interrupt','resume'):
            process = subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',phase,
                                      '--root',str(destination),'--case',case],capture_output=True,text=True,timeout=120)
            expected = 75 if phase == 'interrupt' else 0
            if process.returncode != expected:
                successful = False
                # Tracebacks may contain identifiers/paths; never copy them into
                # distributable evidence. Preserve only the failed phase.
                results.append(dict(case=case,result='failed',phase=phase,evidence='automated-process-kill'))
                break
        if successful:
            results.append(dict(case=case,result='passed',evidence='automated-process-kill'))
    results.extend(_network_checks(folder/'network'))
    try:
        from lightning.runtime.pairing_probe import credential_checks
        checks = credential_checks()
        results.append(dict(case='native-credentials',result='passed' if checks.get('passed') else 'failed',
                            evidence='native-provider' if checks.get('native_provider') else 'development-provider',details=checks))
    except Exception:
        results.append(dict(case='native-credentials',result='unavailable',evidence='native-provider'))
    return dict(format=1,dummy_data=True,platform=platform.system(),python=platform.python_version(),
                cases=results,physical=[dict(case=name,result='unrun',evidence='physical-unrun',instructions=instruction)
                                       for name,instruction in PHYSICAL.items()])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dummy',action='store_true',help='Acknowledge creation of new dummy profiles only')
    parser.add_argument('--root',required=True,type=Path)
    parser.add_argument('--report',type=Path,help='New JSON file; default ROOT/report.json')
    parser.add_argument('--worker',choices=('interrupt','resume'),help=argparse.SUPPRESS)
    parser.add_argument('--case',choices=CASES,help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        _worker(args.root,args.case,args.worker)
        return 0
    if not args.dummy:
        parser.error('--dummy is required; existing profiles are never accepted')
    report = run(args.root)
    _write(args.report or args.root/'report.json',report)
    print(json.dumps(report,indent=2))
    return 1 if any(row['result']=='failed' for row in report['cases']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
