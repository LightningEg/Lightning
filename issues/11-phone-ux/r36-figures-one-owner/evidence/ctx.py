import json, sys
d = json.load(open(sys.argv[1])); labels = sys.argv[2].split("|"); only = sys.argv[3] if len(sys.argv) > 3 else ""
for page, v in d["pages"].items():
    if only and only not in page: continue
    t = v["tokens"]
    for i, tok in enumerate(t):
        for lab in labels:
            if tok.lower().startswith(lab.lower()) and len(tok) < len(lab) + 25:
                print(f"{page:28} {tok!r:32} -> {' ¦ '.join(t[i+1:i+5])[:110]}")
