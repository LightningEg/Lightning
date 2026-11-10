import os, sys, tempfile, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
os.environ['LIGHTNING_PRICES_OFFLINE']='1'; os.environ['LIGHTNING_TODAY']='2026-11-09'
from lightning.runtime.app import profile_app
from lightning.runtime.devices import Devices
from lightning.runtime.http import Host
out={}
keep=[]
for mode,phone in (('pc',False),('phone',True)):
    root=Path(tempfile.mkdtemp())
    h=Host(lambda cfg,root=root,phone=phone:profile_app(cfg,root/'docs',devices=Devices(root/'app',port=0),phone=phone)).start()
    keep.append(h); out[mode]={'launch':h.launch_url,'origin':h.origin}
Path(sys.argv[1]).write_text(json.dumps(out)); print(out, flush=True)
while True: time.sleep(60)
