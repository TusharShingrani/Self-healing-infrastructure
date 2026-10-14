"""Open a lab shell using credentials already held by the user service manager.

python3 tools/lab_shell.py
python3 tools/lab_shell.py python3 tools/lab.py status

No credential values are printed or written to disk. This must run as the
same user as the loop. After reboot, use the masked prompts in live-demo.md
to provide credentials again; this helper cannot recreate them.
"""
import os
import shlex
import subprocess
import sys

NAMES = ('CS_URL', 'CS_KEY', 'CS_SECRET', 'LAB_SSH_KEY',
         'GEMINI_API_KEY', 'HEALER_GEMINI_MODEL')


def main():
    result = subprocess.run(['systemctl', '--user', 'show-environment'],
                            capture_output=True, text=True)
    if result.returncode:
        sys.exit('Cannot read the user service manager. Run this as the loop user.')
    env = os.environ.copy()
    for line in result.stdout.splitlines():
        values = shlex.split(line)
        if len(values) != 1 or '=' not in values[0]:
            continue
        name, value = values[0].split('=', 1)
        if name in NAMES:
            env[name] = value
    missing = [n for n in NAMES[:4] if not env.get(n)]
    if missing:
        sys.exit('Re-enter credentials in memory first. Missing: '+', '.join(missing))
    command = sys.argv[1:] or ['bash', '-i']
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    main()
