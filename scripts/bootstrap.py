"""Fetch frozen upstream and install both editable packages into the active venv."""
import subprocess,sys,argparse
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--locked',action='store_true',help='Use exact tested dependency versions instead of platform resolution')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1];up=root/'vendor/PPTBench'
commit='d64c09f10a4376fa46532dc82048d1b5228e8b76'
if not up.exists():
    up.parent.mkdir(exist_ok=True)
    subprocess.run(['git','clone','https://github.com/Einsia/PPTBench.git',str(up)],check=True)
subprocess.run(['git','-C',str(up),'checkout','--detach',commit],check=True)
lock=root/'requirements.lock'
if args.locked and lock.exists():subprocess.run([sys.executable,'-m','pip','install','-r',str(lock)],check=True)
subprocess.run([sys.executable,'-m','pip','install',*(['--no-deps'] if args.locked else []),'-e',str(up),'-e',str(root)+'[dev]'],check=True)
subprocess.run([sys.executable,'-m','pip','check'],check=True)
