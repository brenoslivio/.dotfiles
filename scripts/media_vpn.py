#!/usr/bin/env python3
"""Restricted WireGuard setup and Proton NAT-PMP renewal; no wg-quick hooks."""
import base64
import configparser
import http.cookiejar
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NAMESPACE = 'media-vpn'
INTERFACE = 'proton0'


class VPNError(ValueError):
    """An operator message that never contains provider output or credentials."""


def run(*args, input=None):
    return subprocess.check_output(args, input=input, text=True, stderr=subprocess.PIPE, timeout=15)


def inside(*args, input=None):
    return run('ip', 'netns', 'exec', NAMESPACE, *args, input=input)


def parse_config(text):
    cfg = configparser.ConfigParser(interpolation=None, strict=True)
    cfg.read_string(text)
    allowed = {'Interface': {'privatekey', 'address', 'dns', 'mtu'},
               'Peer': {'publickey', 'presharedkey', 'allowedips', 'endpoint', 'persistentkeepalive'}}
    if set(cfg.sections()) != set(allowed) or cfg.defaults():
        raise ValueError('Expected one interface and one peer')
    for section, keys in allowed.items():
        if set(cfg[section]) - keys:
            raise ValueError('Unsupported WireGuard option (hooks are not allowed)')
    interface, peer = cfg['Interface'], cfg['Peer']
    for section, key in ((interface, 'privatekey'), (peer, 'publickey'), (peer, 'presharedkey')):
        if key == 'presharedkey' and key not in section:
            continue
        if len(base64.b64decode(section[key], validate=True)) != 32:
            raise ValueError('Invalid WireGuard key')
    addresses = [ipaddress.ip_interface(a.strip()) for a in interface['address'].split(',')]
    addresses = [str(a) for a in addresses if a.version == 4]
    dns = [ipaddress.ip_address(a.strip()) for a in interface['dns'].split(',')]
    dns = [str(a) for a in dns if a.version == 4]
    networks = [ipaddress.ip_network(a.strip()) for a in peer['allowedips'].split(',')]
    if not addresses or not dns or ipaddress.ip_network('0.0.0.0/0') not in networks:
        raise ValueError('IPv4 address, DNS and full tunnel are required')
    endpoint, port = peer['endpoint'].rsplit(':', 1)
    if ipaddress.ip_address(endpoint).version != 4 or not 1 <= int(port) <= 65535:
        raise ValueError('Expected an IPv4 endpoint and valid port')
    mtu = int(interface.get('mtu', '1420'))
    keepalive = int(peer.get('persistentkeepalive', '25'))
    if not 576 <= mtu <= 1500 or not 0 <= keepalive <= 65535:
        raise ValueError('Invalid MTU/keepalive')
    wireguard = (f"[Interface]\nPrivateKey = {interface['privatekey']}\n[Peer]\n"
                 f"PublicKey = {peer['publickey']}\nAllowedIPs = 0.0.0.0/0\n"
                 f"Endpoint = {endpoint}:{int(port)}\nPersistentKeepalive = {keepalive}\n")
    if 'presharedkey' in peer:
        wireguard += f"PresharedKey = {peer['presharedkey']}\n"
    return addresses, dns, mtu, wireguard


def stop():
    # Idempotent cleanup after partial startup; services stop before this namespace.
    subprocess.run(['ip', 'netns', 'delete', NAMESPACE],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def start(web_port):
    source = Path(os.environ['CREDENTIALS_DIRECTORY'])/'wireguard'
    addresses, dns, mtu, wireguard = parse_config(source.read_text())
    stop()
    created_on_host = False
    try:
        run('ip', 'netns', 'add', NAMESPACE)
        # WireGuard's UDP socket retains the host's network namespace after moving.
        run('ip', 'link', 'add', INTERFACE, 'type', 'wireguard')
        created_on_host = True
        run('ip', 'link', 'set', INTERFACE, 'netns', NAMESPACE)
        created_on_host = False
        inside('sysctl', '-qw', 'net.ipv6.conf.all.disable_ipv6=1', 'net.ipv6.conf.default.disable_ipv6=1')
        inside('nft', '-f', '-', input=f'''table inet vpn {{
 chain input {{ type filter hook input priority 0; policy drop;
  iifname "lo" accept
  meta nfproto ipv6 drop
  ct state established,related accept
  iifname "{INTERFACE}" tcp dport {web_port} drop
  iifname "{INTERFACE}" accept
 }}
 chain output {{ type filter hook output priority 0; policy drop;
  oifname "lo" accept
  meta nfproto ipv6 drop
  oifname "{INTERFACE}" accept
 }}
 chain forward {{ type filter hook forward priority 0; policy drop; }}
}}''')
        inside('wg', 'setconf', INTERFACE, '/dev/stdin', input=wireguard)
        for address in addresses:
            inside('ip', 'address', 'add', address, 'dev', INTERFACE)
        inside('ip', 'link', 'set', 'lo', 'up')
        inside('ip', 'link', 'set', INTERFACE, 'mtu', str(mtu), 'up')
        inside('ip', 'route', 'add', 'default', 'dev', INTERFACE)
        Path('/run/media-vpn/resolv.conf').write_text(''.join(f'nameserver {a}\n' for a in dns))
    except Exception:
        stop()
        if created_on_host:
            subprocess.run(['ip', 'link', 'delete', INTERFACE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        raise


def mapped_port(output):
    match = re.search(r'Mapped public port (\d+) protocol', output)
    if not match or not 1 <= int(match[1]) <= 65535:
        raise VPNError('Invalid NAT-PMP mapping')
    return int(match[1])


def forward(web_port, gateway):
    gateway = str(ipaddress.IPv4Address(gateway))
    ports = [mapped_port(run('natpmpc', '-a', '1', '0', protocol, '60', '-g', gateway))
             for protocol in ('udp', 'tcp')]
    if ports[0] != ports[1]:
        raise VPNError('TCP/UDP mappings differ')
    credentials = json.loads((Path(os.environ['CREDENTIALS_DIRECTORY'])/'qbittorrent').read_text())
    origin = f'http://127.0.0.1:{web_port}'
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def post(path, data):
        request = urllib.request.Request(origin+'/api/v2/'+path,
            data=urllib.parse.urlencode(data).encode(), headers={'Origin': origin, 'Referer': origin+'/'})
        with client.open(request, timeout=5) as response:
            return response.read()

    # qBittorrent 5.3 returns an empty login body. The protected update verifies
    # authentication on both old and new releases; never depend on 'Ok.'.
    post('auth/login', credentials)
    try:
        post('app/setPreferences', {'json': json.dumps({'listen_port': ports[0], 'upnp': False, 'random_port': False})})
    finally:
        try:
            post('auth/logout', {})
        except OSError:
            pass
    Path('/run/media-vpn/forwarding.json').write_text(json.dumps({'port': ports[0], 'renewed': int(time.time())})+'\n')


if __name__ == '__main__':
    try:
        if sys.argv[1] == 'start':
            start(int(sys.argv[2]))
        elif sys.argv[1] == 'stop':
            stop()
        elif sys.argv[1] == 'forward':
            forward(int(sys.argv[2]), sys.argv[3])
        else:
            raise ValueError('Unknown command')
    except Exception as error:
        # ConfigParser/subprocess errors can contain key material: never log their text.
        kind = str(error) if isinstance(error, VPNError) else type(error).__name__
        code = f' HTTP {error.code}' if isinstance(error, urllib.error.HTTPError) else ''
        raise SystemExit(f'Media VPN operation failed ({kind}{code}); check private configuration, tunnel and provider availability.') from None
