#!/usr/bin/env python3
"""Sprite Forge: deterministic sprite extraction, atlas assembly and Godot 4 export."""
from __future__ import annotations
import argparse, hashlib, json, math, sys, zipfile
from pathlib import Path
from PIL import Image, ImageDraw

def manifest(path):
    p=Path(path).resolve(); data=json.loads(p.read_text(encoding="utf-8"))
    size=data.get("frame_size")
    if not isinstance(size,list) or len(size)!=2 or not all(isinstance(v,int) and v>0 for v in size):
        raise ValueError("frame_size must be [positive_width, positive_height]")
    if not isinstance(data.get("animations"),list) or not data["animations"]:
        raise ValueError("animations must be a non-empty array")
    names=set()
    for a in data["animations"]:
        if not a.get("name") or a["name"] in names or not a.get("frames"):
            raise ValueError("Each animation needs a unique name and non-empty frames")
        names.add(a["name"])
        for f in a["frames"]:
            r=f.get("rect")
            if not isinstance(r,list) or len(r)!=4 or not all(isinstance(n,int) for n in r) or r[0]<0 or r[1]<0 or r[2]<=0 or r[3]<=0:
                raise ValueError(f"Invalid frame rect: {r}")
    return p,data

def source_path(mp, name):
    p=(mp.parent/name).resolve()
    if not p.is_file() or p.suffix.lower() not in {".png",".jpg",".jpeg",".webp"}:
        raise ValueError(f"Missing or unsupported source image: {p}")
    return p

def inspect_image(path):
    with Image.open(path) as im:
        rgba=im.convert("RGBA"); hist=rgba.getchannel("A").histogram(); total=im.width*im.height
        return {"path":str(path),"format":im.format,"size":[im.width,im.height],"mode":im.mode,
                "has_alpha_band":"A" in im.getbands(),"transparent_pixels":hist[0],
                "partial_alpha_pixels":sum(hist[1:255]),"opaque_pixels":hist[255],
                "transparent_ratio":round(hist[0]/total,4)}

def command_inspect(args):
    print(json.dumps([inspect_image(Path(p)) for p in args.images],indent=2)); return 0

def crop_all(mp,data):
    result={}
    for a in data["animations"]:
        seq=[]
        for f in a["frames"]:
            p=source_path(mp,f["source"])
            with Image.open(p) as im:
                im=im.convert("RGBA"); x,y,w,h=f["rect"]
                if x+w>im.width or y+h>im.height: raise ValueError(f"Crop {f['rect']} exceeds {p} dimensions {im.size}")
                crop=im.crop((x,y,x+w,y+h))
                if crop.getchannel("A").getbbox() is None: raise ValueError(f"Frame in {a['name']} is fully transparent")
                seq.append(crop)
        result[a["name"]]=seq
    return result

def fit_frame(im,size,layout):
    fw,fh=size; pad=layout.get("padding",8)
    if isinstance(pad,int): pl=pt=pr=pb=pad
    elif isinstance(pad,list) and len(pad)==4: pl,pt,pr,pb=pad
    else: raise ValueError("padding must be an integer or [left,top,right,bottom]")
    aw,ah=fw-pl-pr,fh-pt-pb
    if aw<=0 or ah<=0: raise ValueError("Padding leaves no room in frame")
    bbox=im.getchannel("A").getbbox()
    if not bbox: raise ValueError("Cannot fit empty frame")
    sprite=im.crop(bbox); scale=min(aw/sprite.width,ah/sprite.height)
    ns=(max(1,round(sprite.width*scale)),max(1,round(sprite.height*scale)))
    method=Image.Resampling.NEAREST if layout.get("resample","nearest")=="nearest" else Image.Resampling.LANCZOS
    sprite=sprite.resize(ns,method); canvas=Image.new("RGBA",size,(0,0,0,0))
    anchor=layout.get("anchor","bottom_center")
    if anchor=="bottom_center": x=pl+(aw-sprite.width)//2; y=fh-pb-sprite.height
    elif anchor=="center": x=pl+(aw-sprite.width)//2; y=pt+(ah-sprite.height)//2
    elif isinstance(anchor,list) and len(anchor)==2: x=round(anchor[0]*fw-sprite.width/2); y=round(anchor[1]*fh-sprite.height/2)
    else: raise ValueError(f"Unsupported anchor: {anchor}")
    canvas.alpha_composite(sprite,(x,y)); return canvas


def command_extract(args):
    mp,data=manifest(args.manifest); frames=crop_all(mp,data); root=Path(args.output)
    for name,seq in frames.items():
        folder=root/name; folder.mkdir(parents=True,exist_ok=True)
        for i,im in enumerate(seq): im.save(folder/f"{i:02d}.png",optimize=True)
    print(f"Extracted {sum(len(v) for v in frames.values())} source frames into {root}"); return 0


def command_assemble(args):
    mp,data=manifest(args.manifest); size=tuple(data["frame_size"]); frames=crop_all(mp,data)
    out=Path(args.output); (out/"frames").mkdir(parents=True,exist_ok=True); (out/"atlas").mkdir(exist_ok=True)
    processed={}; atlas_frames=[]
    for a in data["animations"]:
        seq=[fit_frame(im,size,a.get("layout",{})) for im in frames[a["name"]]]
        processed[a["name"]]=seq; folder=out/"frames"/a["name"]; folder.mkdir(parents=True,exist_ok=True)
        for i,im in enumerate(seq): im.save(folder/f"{i:02d}.png",optimize=True)
    cols=int(data.get("columns",max(map(len,processed.values()))))
    if cols<1: raise ValueError("columns must be positive")
    rows=sum(math.ceil(len(v)/cols) for v in processed.values()); fw,fh=size
    atlas=Image.new("RGBA",(cols*fw,rows*fh),(0,0,0,0)); row=0; out_anims=[]
    for a in data["animations"]:
        seq=processed[a["name"]]; regions=[]
        for i,im in enumerate(seq):
            x=(i%cols)*fw; y=(row+i//cols)*fh; atlas.alpha_composite(im,(x,y)); regions.append([x,y,fw,fh])
        out_anims.append({"name":a["name"],"fps":float(a.get("fps",8)),"loop":bool(a.get("loop",False)),"frame_count":len(seq),"regions":regions})
        row+=math.ceil(len(seq)/cols)
    asset=data.get("asset","sprite"); atlas_path=out/"atlas"/f"{asset}_atlas.png"; meta_path=out/"atlas"/f"{asset}_frames.json"
    atlas.save(atlas_path,optimize=True)
    meta={"asset":asset,"frame_size":list(size),"columns":cols,"animations":out_anims}
    meta_path.write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print(f"Atlas: {atlas_path} ({atlas.width}x{atlas.height})"); print(f"Manifest: {meta_path}")
    return 0

def command_validate(args):
    meta=json.loads(Path(args.manifest).read_text(encoding="utf-8")); errors=[]
    with Image.open(args.atlas) as im:
        if im.mode!="RGBA": errors.append(f"Expected RGBA atlas, found {im.mode}")
        fw,fh=meta["frame_size"]
        if im.width%fw or im.height%fh: errors.append("Atlas dimensions are not divisible by frame dimensions")
        for a in meta["animations"]:
            hashes={}
            for i,(x,y,w,h) in enumerate(a["regions"]):
                if (w,h)!=(fw,fh) or x<0 or y<0 or x+w>im.width or y+h>im.height:
                    errors.append(f"{a['name']} frame {i}: invalid region"); continue
                frame=im.crop((x,y,x+w,y+h))
                if frame.getchannel("A").getbbox() is None: errors.append(f"{a['name']} frame {i}: empty")
                digest=hashlib.sha256(frame.tobytes()).hexdigest(); hashes.setdefault(digest,[]).append(i)
            for indices in hashes.values():
                if len(indices)>1: print(f"WARNING: {a['name']} has identical frames {indices}")
            if len(a["regions"])!=a["frame_count"]: errors.append(f"{a['name']}: frame count mismatch")
    if errors:
        for e in errors: print("ERROR:",e,file=sys.stderr)
        return 1
    print("PASS: atlas structure and alpha channel validated"); print(json.dumps(inspect_image(Path(args.atlas)),indent=2)); return 0

def command_godot(args):
    meta=json.loads(Path(args.manifest).read_text(encoding="utf-8")); texture=args.texture_path
    if not texture.startswith("res://"): raise ValueError("--texture-path must begin with res://")
    total=sum(len(a["regions"]) for a in meta["animations"]); lines=[f'[gd_resource type="SpriteFrames" load_steps={total+2} format=3]','',f'[ext_resource type="Texture2D" path="{texture}" id="1_atlas"]','']; ids={}
    for a in meta["animations"]:
        safe="".join(c if c.isalnum() else "_" for c in a["name"])
        for i,(x,y,w,h) in enumerate(a["regions"]):
            sid=f"Atlas_{safe}_{i}"; ids[(a["name"],i)]=sid
            lines += [f'[sub_resource type="AtlasTexture" id="{sid}"]','atlas = ExtResource("1_atlas")',f"region = Rect2({x}, {y}, {w}, {h})",'']
    entries=[]
    for a in meta["animations"]:
        fs=", ".join('{"duration": 1.0, "texture": SubResource("'+ids[(a["name"],i)]+'")}' for i in range(len(a["regions"])))
        entries.append('{"frames": ['+fs+'], "loop": '+str(a["loop"]).lower()+', "name": &'+json.dumps(a["name"])+', "speed": '+str(a["fps"])+'}')
    lines += ["[resource]","animations = ["+", ".join(entries)+"]",""]
    dest=Path(args.output); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text("\n".join(lines),encoding="utf-8")
    print(f"Wrote {dest}"); return 0

def command_preview(args):
    mp,data=manifest(args.manifest); frames=crop_all(mp,data); items=[(f"{n} {i:02d}",im) for n,seq in frames.items() for i,im in enumerate(seq)]
    cols=min(4,len(items)); cw,ch=180,210; sheet=Image.new("RGB",(cols*cw,math.ceil(len(items)/cols)*ch),(55,55,62)); draw=ImageDraw.Draw(sheet)
    for i,(label,im) in enumerate(items):
        x=(i%cols)*cw; y=(i//cols)*ch; tile=Image.new("RGBA",(cw-12,ch-38),(0,0,0,0)); im.thumbnail((cw-24,ch-54),Image.Resampling.NEAREST)
        tile.alpha_composite(im,((tile.width-im.width)//2,(tile.height-im.height)//2))
        checker=Image.new("RGBA",tile.size,(0,0,0,0)); d=ImageDraw.Draw(checker)
        for yy in range(0,tile.height,12):
            for xx in range(0,tile.width,12):
                if (xx//12+yy//12)%2==0: d.rectangle((xx,yy,xx+11,yy+11),fill=(105,105,112,255))
        checker.alpha_composite(tile); sheet.paste(checker.convert("RGB"),(x+6,y+5)); draw.text((x+7,y+ch-25),label,fill="white")
    dest=Path(args.output); dest.parent.mkdir(parents=True,exist_ok=True); sheet.save(dest); print(f"Wrote {dest}"); return 0

def command_package(args):
    root=Path(args.input).resolve(); dest=Path(args.output); dest.parent.mkdir(parents=True,exist_ok=True)
    if not root.is_dir(): raise FileNotFoundError(root)
    with zipfile.ZipFile(dest,"w",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob("*")):
            if p.is_file(): z.write(p,p.relative_to(root))
    with zipfile.ZipFile(dest) as z:
        bad=z.testzip()
        if bad: raise RuntimeError(f"ZIP verification failed: {bad}")
    print(f"ZIP verified: {dest}"); return 0

def main():
    p=argparse.ArgumentParser(description="Sprite Forge — deterministic sprite tools for Godot 4")
    sub=p.add_subparsers(dest="cmd",required=True)
    q=sub.add_parser("inspect"); q.add_argument("images",nargs="+"); q.set_defaults(func=command_inspect)
    q=sub.add_parser("extract"); q.add_argument("manifest"); q.add_argument("--output",required=True); q.set_defaults(func=command_extract)
    q=sub.add_parser("assemble"); q.add_argument("manifest"); q.add_argument("--output",required=True); q.set_defaults(func=command_assemble)
    q=sub.add_parser("validate"); q.add_argument("atlas"); q.add_argument("manifest"); q.set_defaults(func=command_validate)
    q=sub.add_parser("godot-resource"); q.add_argument("atlas"); q.add_argument("manifest"); q.add_argument("--texture-path",required=True); q.add_argument("--output",required=True); q.set_defaults(func=command_godot)
    q=sub.add_parser("preview"); q.add_argument("manifest"); q.add_argument("--output",required=True); q.set_defaults(func=command_preview)
    q=sub.add_parser("package"); q.add_argument("input"); q.add_argument("--output",required=True); q.set_defaults(func=command_package)
    args=p.parse_args()
    try: return args.func(args)
    except (OSError,ValueError,json.JSONDecodeError,zipfile.BadZipFile) as e:
        print(f"Sprite Forge error: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
