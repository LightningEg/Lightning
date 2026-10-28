#!/usr/bin/env python3
"""Import authentic Egyptian wallet, fintech and investment logos into the institutions catalog.

This is an offline asset build step: the shipped app does not download images.
Run: python tools/import_egypt_wallet_logos.py
Requires requests, pillow. CairoSVG is optional for SVG source artwork.
"""
from __future__ import annotations
import csv
import io
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "institutions-logos"
INSTITUTIONS = ROOT / "lightning" / "ui" / "static" / "institutions"
CSV = ROOT / "lightning" / "accounts" / "institutions.csv"
BALAD = "https://www.balad.me/logos/wallets/"
# id, display name, category, canonical source URL, provenance, optional app institution code
SOURCES = [
    ("vodafone-cash","Vodafone Cash","telecom_wallet",BALAD+"vodafone-cash-combined.png","wallet-directory","vodafone-cash"),
    ("orange-cash","Orange Cash","telecom_wallet",BALAD+"orange.png","wallet-directory","orange-cash"),
    ("etisalat-cash","e& Cash","telecom_wallet",BALAD+"etisalat.webp","wallet-directory","etisalat-cash"),
    ("we-pay","WE Pay","telecom_wallet",BALAD+"we.png","wallet-directory","we-pay"),
    ("nbe-phone-cash","NBE Phone Cash","bank_wallet",BALAD+"nbe_phone_cash.jpeg","wallet-directory",None),
    ("bm-wallet","Banque Misr Wallet","bank_wallet",BALAD+"bm.png","wallet-directory",None),
    ("qnb-wallet","QNB Wallet","bank_wallet",BALAD+"qnb_wallet.jpeg","wallet-directory",None),
    ("saib-wallet","SAIB Wallet","bank_wallet",BALAD+"saib.jpg","wallet-directory",None),
    ("aib-wallet","AIB Wallet","bank_wallet",BALAD+"aib.webp","wallet-directory",None),
    ("faisal-cash","Faisal Cash","bank_wallet",BALAD+"fisal.png","wallet-directory",None),
    ("cib-smartwallet","CIB SmartWallet","bank_wallet",BALAD+"cib_smartwallet.jpeg","wallet-directory",None),
    ("banki-wallet","Banki Wallet","bank_wallet",BALAD+"banki_wallet.jpeg","wallet-directory",None),
    ("qahera-cash","Qahera Cash","bank_wallet",BALAD+"qaheeracash.jpeg","wallet-directory",None),
    ("nbk-wallet","NBK Wallet","bank_wallet",BALAD+"nbk.jpeg","wallet-directory",None),
    ("adib-wallet","ADIB Wallet","bank_wallet",BALAD+"adib.jpg","wallet-directory",None),
    ("cash2go","Cash 2GO","bank_wallet",BALAD+"cash2go.png","wallet-directory",None),
    ("audi2pay","Audi2Pay","bank_wallet",BALAD+"audi2pay.jpeg","wallet-directory",None),
    ("halan-cash","Halan Cash","fintech_wallet",BALAD+"halan.jpg","wallet-directory",None),
    ("e-pocket","e-Pocket","fintech_wallet",BALAD+"e-pocket.jpeg","wallet-directory",None),
    ("masary","Masary","payment_service",BALAD+"masary-logo.jpg","wallet-directory",None),
    ("easycash","easyCash","fintech_wallet",BALAD+"easycash.png","wallet-directory",None),
    ("axis","Axis","fintech_wallet",BALAD+"axislogo.webp","wallet-directory",None),
    ("telda","Telda","finance_app","https://telda.app/_next/static/media/telda-icon.f39ac0de.png","official","telda"),
    ("thndr","Thndr","investment_app","https://thndr.app/wp-content/uploads/2024/01/Thndr_Logo_Final_Thndr_Lockup_Yellow-1.png","official","thndr"),
    ("money-fellows","Money Fellows","savings_app","https://moneyfellows.com/media/2xmlxxks/header-logo.png","official",None),
    ("instapay","InstaPay","payment_service","https://www.instapay.eg/wp-content/uploads/2022/03/logo.png","official",None),
    ("fawry","Fawry","payment_service","https://www.fawry.com/wp-content/uploads/2023/05/fawry-Logo.png","official","fawry"),
    ("paymob","Paymob","payment_service","https://paymob.com/images/paymobLogo.png","official",None),
    ("halan","Halan","finance_app","https://halan.com/wp-content/themes/halan/app/images/Full-logo-black-version.svg","official",None),
    ("khazna","Khazna","finance_app","https://khazna.app/assets/svgs/logo.svg","official",None),
    ("valu","valU","finance_app","https://valugroup.com/icon.svg","official","valu"),
]
REQUIRED = {"vodafone-cash","orange-cash","etisalat-cash","we-pay","telda","thndr","money-fellows","instapay"}

def source(session, url):
    resp = session.get(url, timeout=(15, 35), allow_redirects=True)
    resp.raise_for_status()
    raw = resp.content
    if not 300 <= len(raw) <= 8_000_000:
        raise ValueError("unexpected source file size")
    suffix = urlparse(url).path.rsplit(".", 1)[-1].lower()
    if suffix == "svg":
        import cairosvg
        lowered = raw.lower()
        if b"<script" in lowered or b"<!entity" in lowered:
            raise ValueError("SVG contains active content")
        raw = cairosvg.svg2png(bytestring=raw, output_width=512)
    im = Image.open(io.BytesIO(raw))
    im.load()
    if im.width < 24 or im.height < 24 or im.width * im.height > 20_000_000:
        raise ValueError("bad image dimensions")
    fmt = im.format
    if fmt not in ("PNG", "JPEG", "WEBP"):
        raise ValueError("unsupported image format")
    ext = {"PNG":"png","JPEG":"jpg","WEBP":"webp"}[fmt]
    return ImageOps.exif_transpose(im).convert("RGBA"), raw, ext

def tile(im, dimensions, pad, white=False):
    out = Image.new("RGBA", dimensions, (255,255,255,255) if white else (0,0,0,0))
    small = ImageOps.contain(im, (dimensions[0]-pad*2,dimensions[1]-pad*2), Image.Resampling.LANCZOS)
    out.alpha_composite(small, ((dimensions[0]-small.width)//2,(dimensions[1]-small.height)//2))
    return out

def main():
    for dirname in ("icons","wordmarks","originals"):
        (ASSETS/dirname).mkdir(parents=True, exist_ok=True)
    INSTITUTIONS.mkdir(parents=True, exist_ok=True)
    manifest_path = ASSETS/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = {}
    errors = []
    s = requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0 (compatible; LightningAssetCatalog/1.0; logo archive)"})
    for slug,name,category,url,origin,institution_code in SOURCES:
        try:
            im,raw,ext=source(s,url)
            (ASSETS/"originals"/(slug+"."+ext)).write_bytes(raw)
            tile(im,(256,256),12,white=True).save(ASSETS/"icons"/(slug+".png"),optimize=True)
            tile(im,(512,192),12).save(ASSETS/"wordmarks"/(slug+".png"),optimize=True)
            manifest[slug]={
                "name":name,"category":category,"icon":"icons/"+slug+".png",
                "wordmark":"wordmarks/"+slug+".png",
                "original":"originals/"+slug+"."+ext,
                "source_url":url,"source_type":origin,
            }
            if institution_code:
                small=tile(im,(64,64),3,white=True)
                for colors in (128,64,32):
                    buf=io.BytesIO()
                    small.quantize(colors,method=Image.Quantize.FASTOCTREE).save(buf,"PNG",optimize=True)
                    if len(buf.getvalue())<=8192:
                        (INSTITUTIONS/(institution_code+".png")).write_bytes(buf.getvalue())
                        results[institution_code]=institution_code+".png"
                        break
            print("OK",slug,im.size,flush=True)
        except Exception as exc:
            errors.append({"id":slug,"error":str(exc)[:250],"source_url":url})
            print("FAILED",slug,repr(exc),flush=True)
    missing=REQUIRED.difference(manifest)
    if missing:
        raise RuntimeError("Required brand source images failed: "+", ".join(sorted(missing)))
    rows=list(csv.DictReader(CSV.open(encoding="utf-8",newline="")))
    for row in rows:
        if row["code"] in results:
            row["logo"]=results[row["code"]]
    with CSV.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    rp=ASSETS/"download-report.json"
    report=json.loads(rp.read_text(encoding="utf-8"))
    report.update({"wallet_fintech_expected":len(SOURCES),"wallet_fintech_imported":len(SOURCES)-len(errors),"wallet_fintech_failures":errors})
    rp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Added {len(SOURCES)-len(errors)} finance logos; app institution images: {len(results)}")

if __name__ == "__main__":
    main()
