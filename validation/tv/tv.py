import base64
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path('/tmp/moonshine-tv-validation')
CONF = '/media/developer/apps/usr/palm/applications/com.limelight.webos/conf/'

def remote(command):
    r = subprocess.run(['ssh', '-tt', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', '-o', 'LogLevel=ERROR', 'tv', command], capture_output=True, text=True, timeout=15)
    if r.returncode:
        raise RuntimeError(r.stderr + r.stdout)
    return r.stdout

def luna(method, payload):
    return remote('luna-send -n 1 -w 3000 -f luna://' + method + ' ' + shlex.quote(json.dumps(payload)))

def write(name, data):
    encoded = base64.b64encode(data).decode()
    remote('printf %s ' + shlex.quote(encoded) + ' | base64 -d > ' + shlex.quote(CONF + name))

def backup():
    for name in ('hosts.ini', 'moonlight.ini'):
        p = ROOT / (name + '.original')
        if not p.exists():
            p.write_bytes(base64.b64decode(remote('base64 ' + shlex.quote(CONF + name))))

def close():
    print(luna('com.webos.service.applicationmanager/closeByAppId', {'id':'com.limelight.webos'}))
    remote("i=0; while ps -ef | grep '[b]in/moonlight' >/dev/null; do i=$((i+1)); [ $i -ge 50 ] && exit 1; sleep 0.1; done; true")

if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'configure':
        backup()
        close()
        uuid = (ROOT/'uuid').read_text().strip()
        hosts = (ROOT/'hosts.ini.original').read_text().replace('selected = true', 'selected = false')
        hosts += f'\n[{uuid}]\nmac = 2c:f0:5d:8c:a2:ca\nhostname = Alpha async validation\naddress = 192.168.0.18:1717\nselected = true\n'
        config = (ROOT/'moonlight.ini.original').read_text()
        for key, value in {'width':sys.argv[2], 'height':sys.argv[3], 'net_fps':'60', 'bitrate':'150000', 'hdr':sys.argv[4]}.items():
            config, count = re.subn(rf'(?m)^{key}\s*=.*$', f'{key} = {value}', config)
            assert count == 1, key
        write('hosts.ini', hosts.encode())
        write('moonlight.ini', config.encode())
        print(luna('com.webos.audio/setMuted', {'muted':True}))
    elif action == 'launch':
        print(luna('com.webos.applicationManager/launch', {'id':'com.limelight.webos','params':{'host_uuid':(ROOT/'uuid').read_text().strip(),'host_app_id':int(sys.argv[2])}}))
    elif action == 'close':
        close()
    elif action == 'restore':
        close()
        for name in ('hosts.ini', 'moonlight.ini'):
            write(name, (ROOT/(name+'.original')).read_bytes())
        print(luna('com.webos.audio/setMuted', {'muted':True}))
        print(luna('com.webos.audio/getVolume', {}))
