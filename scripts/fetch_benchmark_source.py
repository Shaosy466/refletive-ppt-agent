#!/usr/bin/env python3
"""Fetch only pinned public upstream code. Never executes downloaded code.

Usage: python scripts/fetch_benchmark_source.py LongPuzzleBench
Uses the lock checked into this repository; preserves any existing destination.
"""
import argparse,hashlib,json,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('name');args=parser.parse_args()
    sources=json.loads((ROOT/'configs/benchmark-sources.lock.json').read_text())['sources']
    if args.name not in sources:parser.error('No verified source lock for '+args.name)
    spec=sources[args.name];dest=ROOT/'vendor'/args.name
    if dest.exists():raise SystemExit(f'Refusing to overwrite existing source: {dest}')
    dest.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as temp:
        archive=Path(temp)/'source.tar.gz'
        subprocess.run(['curl','--fail','--location','--retry','2','--max-time','900',
            f'https://codeload.github.com/{spec["repo"]}/tar.gz/{spec["commit"]}', '-o',str(archive)],check=True)
        # SHA is recorded, but API/codeload archives may have different root names
        # and compression bytes. The immutable commit in the URL pins content.
        checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
        with tarfile.open(archive) as tf:
            members=tf.getmembers();top=members[0].name.split('/')[0]
            for member in members:
                p=Path(member.name)
                if p.is_absolute() or '..' in p.parts or member.issym() or member.islnk():raise ValueError('Unsafe archive entry')
            tf.extractall(Path(temp)/'unpack',filter='data')
        unpacked=Path(temp)/'unpack'/top
        (unpacked/'.source-lock.json').write_text(json.dumps({'repo':spec['repo'],'commit':spec['commit'],'archive_sha256':checksum},indent=2))
        unpacked.rename(dest)
    print(dest)
if __name__=='__main__':main()
