import datetime
import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path
from tv import ROOT, CONF, close, luna, remote

PYTHON = sys.executable

def uptime():
    return float(remote('cut -d " " -f 1 /proc/uptime').strip())

def cancel():
    return remote('curl -ksS --max-time 5 --cert ' + CONF + 'key/client.pem --key ' + CONF + 'key/key.pem https://192.168.0.18:1718/cancel')

cases = [('hdr4k',3840,2160,True,622077751),
         ('sdr1440',2560,1440,False,1920635167),
         ('sdr4k',3840,2160,False,1920635167),
         ('hdr4k-composite',3840,2160,True,855828582),
         ('hdr4k-transitions',3840,2160,True,1807225950),
         ('hdr4k-windows',3840,2160,True,174940389),
         ('hdr4k-reconnect',3840,2160,True,622077751)]
cases.insert(0, ('hdr1440',2560,1440,True,622077751))
parser=argparse.ArgumentParser()
parser.add_argument('--only')
parser.add_argument('--label',required=True)
args=parser.parse_args()
if args.only:
    cases=[c for c in cases if c[0] in args.only.split(',')]
try:
    for name,w,h,hdr,app in cases:
        print(name, flush=True)
        close();cancel();time.sleep(2)
        subprocess.run([PYTHON,str(ROOT/'tv.py'),'configure',str(w),str(h),str(hdr).lower()],check=True,stdout=subprocess.DEVNULL)
        initial = uptime()
        result = {'case':name,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'variant':args.label,'uptime_initial':initial,'samples':[],'screenshot_method':'DISPLAY'}
        response = luna('com.webos.applicationManager/launch', {'id':'com.limelight.webos','params':{'host_uuid':(ROOT/'uuid').read_text().strip(),'host_app_id':app}})
        result['launch_response']=response
        for i in range(6):
            time.sleep(5)
            now=uptime()
            result['samples'].append({'uptime':now,'host_load':Path('/proc/loadavg').read_text().strip()})
            if i == 3:
                result['overlay']=luna('com.webos.service.networkinput/sendSpecialKey',{'key':'RED'})
            if i in (3,5):
                result[f'capture_{i}']=luna('com.webos.service.capture/executeOneShot',{'path':'/tmp/moonshine-validation.png','method':'DISPLAY','format':'PNG','width':1920,'height':1080})
                (ROOT/f'{args.label}-{name}-{i}.png').write_bytes(base64.b64decode(remote('base64 /tmp/moonshine-validation.png')))
            if now < initial:
                luna('com.webos.audio/setMuted',{'muted':True})
                result['reboot_detected']=True
                (ROOT/(args.label+'-'+name+'.json')).write_text(json.dumps(result,indent=2))
                raise RuntimeError('TV rebooted; stop rather than repeat')
            if name == 'hdr4k-reconnect' and i == 1:
                close()
                time.sleep(1)
                result['relaunch_response'] = luna('com.webos.applicationManager/launch', {'id':'com.limelight.webos','params':{'host_uuid':(ROOT/'uuid').read_text().strip(),'host_app_id':app}})
                result['relaunch_without_host_cancel'] = True
        result['reboot_detected']=False
        result['mute']=luna('com.webos.audio/getVolume',{})
        result['client_process']=remote('ps -ef | grep /bin/moonlight | grep -v grep')
        (ROOT/(args.label+'-'+name+'.json')).write_text(json.dumps(result,indent=2))
        print(cancel(), flush=True)
finally:
    subprocess.run([PYTHON,str(ROOT/'tv.py'),'restore'],check=True)
