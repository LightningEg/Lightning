#!/usr/bin/env python3
"""Download actual Egyptian bank logo artwork into assets/bank-logos (one-time)."""
import io, json, sys
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
ROOT=Path(__file__).resolve().parent.parent
TARGET=ROOT/"assets"/"bank-logos"
LOGOS={
"abk":"abk","cib":"cib","arab-bank":"arab-bank","aaib":"aaib","aib":"aib",
"ealb":"ealb","saib":"saib","abc":"abc","united-bank":"united-bank",
"fabmisr":"fab","adcb":"adcb","hsbc":"hsbc","alexbank":"bank-of-alexandria",
"emirates-nbd":"emirates-nbd","attijariwafa":"attijariwafa","hdb":"hdb",
"ebank":"edbe","egbank":"eg-bank","banque-du-caire":"banque-du-caire",
"nbk":"nbk","mashreq":"mashreq","standard-chartered":"standard-chartered",
"citibank":"citibank","qnb":"qnb","suez-canal":"suez-canal-bank",
"credit-agricole":"credit-agricole","midbank":"midbank","bank-nxt":"bank-nxt",
"nbe":"nbe","banque-misr":"banque-misr","adib":"adib","albaraka":"al-baraka",
"faisal":"faisal-bank","kfh":"kfh","abe":"abe","idb":"idb",
}
def main():
    originals=TARGET/"originals";icons=TARGET/"icons";wordmarks=TARGET/"wordmarks"
    for d in [originals,icons,wordmarks]:d.mkdir(parents=True,exist_ok=True)
    s=requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0 (compatible; LightningBankLogoAssetImport/1.0)","Accept":"image/webp,image/png,image/jpeg,*/*","Referer":"https://banksegypt.com/banks"})
    s.mount("https://",HTTPAdapter(max_retries=Retry(total=3,backoff_factor=1,status_forcelist=[429,500,502,503,504])))
    entries=[(slug,"https://banksegypt.com/assets/img/egbanks/"+file+".webp","webp","third-party directory") for slug,file in LOGOS.items()]
    entries.append(("onebank","https://www.onebank.eg/resources/img/favicon/android-icon-192x192.png","png","official bank site"))
    mapping={};failed=[]
    for n,(slug,url,ext,provenance) in enumerate(entries,1):
        try:
            resp=s.get(url,timeout=(15,45));resp.raise_for_status()
            if len(resp.content)>10_000_000:raise ValueError("Oversized file")
            with Image.open(io.BytesIO(resp.content)) as image:image.verify()
            with Image.open(io.BytesIO(resp.content)) as image:im=ImageOps.exif_transpose(image).convert("RGBA")
            if im.width*im.height>12_000_000:raise ValueError("Oversized image")
            (originals/(slug+"."+ext)).write_bytes(resp.content)
            word=im.copy();word.thumbnail((488,168),Image.Resampling.LANCZOS)
            canvas=Image.new("RGBA",(512,192),(0,0,0,0))
            canvas.alpha_composite(word,((512-word.width)//2,(192-word.height)//2))
            canvas.save(wordmarks/(slug+".png"),optimize=True)
            tile=Image.new("RGBA",(256,256),(0,0,0,0))
            ImageDraw.Draw(tile).rounded_rectangle((3,3,252,252),radius=45,fill="white")
            small=im.copy();small.thumbnail((216,216),Image.Resampling.LANCZOS)
            tile.alpha_composite(small,((256-small.width)//2,(256-small.height)//2))
            tile.save(icons/(slug+".png"),optimize=True)
            mapping[slug]={"icon":"icons/"+slug+".png","wordmark":"wordmarks/"+slug+".png","original":"originals/"+slug+"."+ext,"source_url":url,"source_type":provenance}
            print(f"{n}/{len(entries)} OK {slug}: {im.width}x{im.height}",flush=True)
        except Exception as e:
            failed.append(slug)
            print(f"ERROR {slug}: {e}",file=sys.stderr,flush=True)
    try:
        svg=s.get("https://www.onebank.eg/resources/img/logo_onebank.svg",timeout=(15,45))
        svg.raise_for_status()
        if svg.content.lstrip().startswith((b"<svg",b"<?xml")) and len(svg.content)<2_000_000:
            (originals/"onebank-wordmark.svg").write_bytes(svg.content)
            if "onebank" in mapping:mapping["onebank"]["original_svg"]="originals/onebank-wordmark.svg"
    except Exception as e:print("Optional onebank SVG failed:",e,flush=True)
    (TARGET/"manifest.json").write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (TARGET/"download-report.json").write_text(json.dumps({"imported":len(mapping),"expected":len(entries),"failed":failed},indent=2)+"\n",encoding="utf-8")
    print(f"Imported {len(mapping)}/{len(entries)}; errors: {failed}",flush=True)
    return int(bool(failed))
if __name__=="__main__":raise SystemExit(main())
