"""Cosmetics are account entitlements, never device or money permissions."""
import base64
import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from lightning.security.cosmetic_license import verify_license, InvalidCosmeticLicense
from lightning.security.cosmetic_parts import validate_parts, InvalidCosmeticParts

PROFILE = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
BUNDLES = Path(__file__).resolve().parents[1] / 'lightning/ui/static/cosmetics'

@pytest.fixture
def license():
    key = Ed25519PrivateKey.generate()
    data = {'issuer':'lightning-store','schema_version':1,'account_id':str(uuid4()),'profile_id':PROFILE,
            'items':[{'item_id':'nile','asset_version':1,'deliveries':[]}]}
    def sign(data):
        payload=json.dumps(data,separators=(',',':'))
        return {'algorithm':'Ed25519','key_id':'test','payload':payload,
                'signature':base64.urlsafe_b64encode(key.sign(payload.encode())).decode().rstrip('=')}
    return data,sign,{'test':key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}

def test_same_entitlement_is_portable_and_permanent(license):
    data,sign,keys=license
    envelope=sign(data)
    for _device in ('phone','pc','replacement-pc'):  # one profile, any of its devices
        owned=verify_license(envelope,keys,{'nile':1},expected_account=data['account_id'],expected_profile=PROFILE)
        assert owned.items == (('nile',1),) and owned.profile_id == PROFILE
    assert 'expires' not in envelope['payload'] and 'device' not in envelope['payload']

def test_a_licence_is_for_its_own_profile_only(license):
    data,sign,keys=license
    other='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
    with pytest.raises(InvalidCosmeticLicense,match='different profile'):
        verify_license(sign(data),keys,{'nile':1},expected_profile=other)
    for bad in (None,'','not-a-uuid','aaaaaaaa-aaaa-1aaa-8aaa-aaaaaaaaaaaa',5):
        broken={k:v for k,v in data.items() if k!='profile_id'}
        if bad is not None:broken['profile_id']=bad
        with pytest.raises(InvalidCosmeticLicense,match='no profile'):
            verify_license(sign(broken),keys,{'nile':1},expected_profile=PROFILE)

@pytest.mark.parametrize('change',['signature','key','algorithm','account','version','tamper','oversize'])
def test_bad_claims_fail_closed(license,change):
    data,sign,keys=license;e=sign(data);expected=data['account_id']
    if change=='signature':e['signature']='A'*86
    elif change=='key':keys={}
    elif change=='algorithm':e['algorithm']='none'
    elif change=='account':expected=str(uuid4())
    elif change=='version':data['items'][0]['asset_version']=2;e=sign(data)
    elif change=='tamper':e['payload']=e['payload'].replace('nile','royal-obsidian-gold')
    else:e['payload']='x'*131073
    with pytest.raises(InvalidCosmeticLicense):verify_license(e,keys,{'nile':1},expected_account=expected)

def test_bundled_parts_are_data_only_and_partial_themes_fall_back():
    contract=json.loads((BUNDLES/'slots.json').read_text())
    for name in ('nile','royal-obsidian-gold'):
        manifest=json.loads((BUNDLES/(name+'.json')).read_text())
        assert validate_parts(manifest,contract) == manifest
        minimal=copy.deepcopy(manifest);minimal['parts']={}
        assert validate_parts(minimal,contract)['parts'] == {}
        for slot,key,value in [('layout','width','900px'),('controls','fill','url(https://example.test)'),('decoration','motion','run-javascript')]:
            bad=copy.deepcopy(manifest);bad['parts'][slot]={key:value}
            with pytest.raises(InvalidCosmeticParts):validate_parts(bad,contract)

def test_fallback_is_complete_and_unknown_theme_rolls_back_as_a_whole():
    from lightning.security.cosmetic_parts import resolve_parts
    contract=json.loads((BUNDLES/'slots.json').read_text())
    baseline=json.loads((BUNDLES/'lightning-default.json').read_text())
    theme=json.loads((BUNDLES/'nile.json').read_text())
    theme['parts']={'palette':{'accent':'#3FD0E0'}}
    parts,fallback=resolve_parts(theme,baseline,contract)
    assert not fallback and parts['palette']['accent']=='#3FD0E0'
    assert parts['palette']['surface']==baseline['parts']['palette']['surface']
    assert baseline['parts']['palette']['accent']=='#0B6DD6'  # no mutation
    theme['parts']['layout']={'width':'900px'}
    parts,fallback=resolve_parts(theme,baseline,contract)
    assert fallback and parts==baseline['parts']
    for malformed in (None,[],{'schemaVersion':True}, {'schemaVersion':1,'id':[],'version':1}):
        parts,fallback=resolve_parts(malformed,baseline,contract)
        assert fallback and parts==baseline['parts']

def test_each_part_can_come_from_a_different_owned_theme():
    from lightning.security.cosmetic_parts import compose_parts
    contract=json.loads((BUNDLES/'slots.json').read_text())
    baseline=json.loads((BUNDLES/'lightning-default.json').read_text())
    catalog={name:json.loads((BUNDLES/(name+'.json')).read_text()) for name in ('nile','royal-obsidian-gold')}
    selected={'palette':'nile','cards':'royal-obsidian-gold','brand':'lightning-default'}
    parts=compose_parts(selected,baseline,catalog,{name:1 for name in catalog},contract)
    assert parts['palette']==catalog['nile']['parts']['palette']
    assert parts['cards']==catalog['royal-obsidian-gold']['parts']['cards']
    assert parts['brand']==baseline['parts']['brand']
    with pytest.raises(InvalidCosmeticParts,match='not owned'):
        compose_parts(selected,baseline,catalog,{'nile':1},contract)
    with pytest.raises(InvalidCosmeticParts,match='not owned'):
        compose_parts(selected,baseline,catalog,{name:2 for name in catalog},contract)
    assert baseline['parts']['palette']['accent']=='#0B6DD6'
