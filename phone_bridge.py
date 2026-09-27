#!/usr/bin/env python3
"""Reconnect only the paired phone and maintain its fixed localhost camera address."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
import time

CONFIG = Path.home()/'.config/uconsole-camera/phone.json'
STATUS = Path.home()/'.local/state/uconsole-camera/phone.json'


def adb(*args, timeout=8):
    result = subprocess.run(['adb', *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Phone connection unavailable')
    return result.stdout.strip()


def network_key():
    result = subprocess.run(['ip','-j','-4','addr','show','up'],capture_output=True,text=True,timeout=5,check=True)
    return tuple(sorted(info['local'] for interface in json.loads(result.stdout)
                        for info in interface.get('addr_info',[]) if info.get('scope') == 'global'))


class Discovery:
    def __init__(self, serial):
        from zeroconf import IPVersion, ServiceBrowser, Zeroconf
        self.serial, self.lock, self.found = serial, threading.Lock(), {}
        self.zc = Zeroconf(ip_version=IPVersion.V4Only)
        self.browser = ServiceBrowser(self.zc, '_adb-tls-connect._tcp.local.', listener=self)

    def add_service(self, zc, type_, name):
        if not name.startswith('adb-'+self.serial+'-'):
            return
        info = zc.get_service_info(type_, name, timeout=2500)
        if info:
            with self.lock:
                self.found[name] = [f'{address}:{info.port}' for address in info.parsed_addresses() if ':' not in address]

    def update_service(self, zc, type_, name):
        self.add_service(zc, type_, name)

    def remove_service(self, zc, type_, name):
        with self.lock:
            self.found.pop(name, None)

    def endpoints(self):
        with self.lock:
            return [address for values in self.found.values() for address in values]

    def close(self):
        self.browser.cancel()
        self.zc.close()


def save_status(value):
    STATUS.parent.mkdir(parents=True,exist_ok=True)
    temporary=STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps({'updated':time.time(),**value}))
    temporary.replace(STATUS)


def open_phone():
    config=json.loads(CONFIG.read_text())
    state=json.loads(STATUS.read_text())
    if not state.get('connected') or time.time()-state['updated']>30:
        raise RuntimeError('Phone is not connected. Use the same Wi-Fi with Wireless debugging on, or connect it by USB.')
    target=state['target']
    if adb('-s',target,'shell','getprop','ro.serialno') != config['serial']:
        raise RuntimeError('The connected phone does not match the paired phone.')
    adb('-s',target,'shell','am','start','-a','android.intent.action.VIEW','-d','http://127.0.0.1:8765/phone.html')
    print('Phone camera page opened. Tap Start camera on the phone.')


def run():
    config=json.loads(CONFIG.read_text())
    serial=config['serial']
    fallback=config.get('last_endpoint')
    discovery=None
    previous_network=None
    selected=None
    next_connect=0.
    while True:
        try:
            network=network_key()
            if network != previous_network:
                if discovery:
                    discovery.close()
                discovery=Discovery(serial)
                previous_network=network
            endpoints=discovery.endpoints()
            if fallback and fallback not in endpoints:
                endpoints.append(fallback)
            devices={line.split()[0]:line.split()[1] for line in adb('devices').splitlines()[1:] if len(line.split())>=2}
            available=[target for target in [serial,*endpoints] if devices.get(target)=='device']
            if not available and time.monotonic()>=next_connect:
                for target in endpoints[:3]:
                    try:
                        adb('connect',target,timeout=5)
                    except (RuntimeError,subprocess.TimeoutExpired):
                        pass
                next_connect=time.monotonic()+10
                devices={line.split()[0]:line.split()[1] for line in adb('devices').splitlines()[1:] if len(line.split())>=2}
                available=[target for target in [serial,*endpoints] if devices.get(target)=='device']
            target=available[0] if available else None
            if target:
                changed = target != selected
                if changed:
                    if adb('-s',target,'shell','getprop','ro.serialno') != serial:
                        raise RuntimeError('Discovered device does not match the paired phone')
                    selected=target
                mappings=adb('-s',target,'reverse','--list')
                if changed or not any(line.split()[-2:]==['tcp:8765','tcp:8765'] for line in mappings.splitlines()):
                    adb('-s',target,'reverse','tcp:8765','tcp:8765')
                save_status({'connected':True,'target':target,'connection':'USB' if target==serial else 'Wi-Fi'})
            else:
                selected=None
                save_status({'connected':False,'message':'Waiting for paired phone'})
        except Exception as exc:
            selected=None
            save_status({'connected':False,'message':str(exc)})
        time.sleep(5)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--open',action='store_true')
    args=parser.parse_args()
    if args.open:
        try:
            open_phone()
        except Exception as exc:
            raise SystemExit(str(exc))
    else:
        run()
