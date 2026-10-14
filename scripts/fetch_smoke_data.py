#!/usr/bin/env python3
"""Download public smoke inputs only; never download hidden reference meshes."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('benchmark',choices=['a2z','edithero']);a=p.parse_args()
    if a.benchmark=='a2z':
        repo='KRAFTON/A2Z-GameSpec-Bench';revision='74343b5fa8522b4167a355bedbe8c004cb7450e2';files=['gdds/small/bin_bit.md']
    else:
        repo='AlayaLab/EditHero';revision='dba807e8c98f995bc0fad144da38b574d4539fb5'
        files=['sample/chain.json','sample/README.md','sample/data/states/A/1a3267df_s0/turn00.glb']
        files += [f'sample/data/renders/A/1a3267df_s0/turn{i:02d}/view0_cond.png' for i in range(1,6)]
    dest=ROOT/'data'/a.benchmark;hashes={}
    for name in files:
        target=dest/name;target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+'.download')
        subprocess.run(['curl','--fail','--location','--retry','2','--max-time','180',
                       f'https://huggingface.co/datasets/{repo}/resolve/{revision}/{name}','-o',str(temporary)],check=True)
        temporary.replace(target);hashes[name]=hashlib.sha256(target.read_bytes()).hexdigest()
    (dest/'source-lock.json').write_text(json.dumps({'repo':repo,'revision':revision,'files':hashes},indent=2))
    print(dest)
if __name__=='__main__':main()
