"""Refuse publication when changed files contain known runtime credentials."""
import os
import re
import subprocess
from pathlib import Path

names=('CS_KEY','CS_SECRET','GEMINI_API_KEY')
secrets=[os.environ.get(name,'') for name in names]
files=subprocess.check_output(['git','diff','--name-only'],text=True).splitlines()
files+=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
for name in sorted(set(files)):
    path=Path(name)
    if not path.is_file():continue
    data=path.read_bytes()
    if any(value and value.encode() in data for value in secrets) or re.search(
            rb'(?m)^-----BEGIN (OPENSSH|RSA|EC) PRIVATE KEY-----',data):
        raise RuntimeError('Publication refused: credential material in '+name)
print('Changed-file credential scan passed; no credential values printed')
