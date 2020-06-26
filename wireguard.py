import io
import ipaddress
import os
from pyinfra import host
from pyinfra.operations import files, pkg, python, server
from pyinfra.api.exceptions import OperationError

import clients

NETWORK = ipaddress.ip_network('10.66.0.0/24')
SERVER = NETWORK[1]
PORT = 51820
WG_IF = 'wg0'

os.makedirs("out", exist_ok=True)

def is_snapshot():
    return host.fact.command('sysctl -n kern.version').find('-current ') >= 0

if not (host.fact.os_version >= '6.8' or \
        (host.fact.os_version == '6.7' and is_snapshot())):
    raise OperationError('OpenBSD release too old')

PKG_PATH = f"https://ftp.openbsd.org/pub/OpenBSD/snapshots/packages/{host.fact.arch}/" if is_snapshot() else None

DEFAULT_IF = host.fact.command(
    '''route -n show -inet | awk '/^default/ { print $NF; exit }' ''')

pkg.packages(
    {'Install wireguard tools'},
    ['wireguard-tools'],
    pkg_path=PKG_PATH,
)

files.directory(
    {'Create wireguard configuration directory'},
    '/etc/wireguard',
    user='root', group='wheel', mode='600'
)

server.shell(
    {'Generate server keys'},
    '''
    if ! test -f /etc/wireguard/server.key; then (
      umask 0077
      wg genkey > /etc/wireguard/server.key
      wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub
    ); fi
    '''
)

files.get(
    {'Retrieve server public key'},
    '/etc/wireguard/server.pub',
    'out/server.pub'
)

def generate_client_config(state, host):
    with open("out/server.pub") as f:
        server_pub = f.read().strip()
    for i, client in enumerate(clients.CLIENTS, start=2):
        if client is None:
            continue
        if not os.path.exists(f"out/{client}.key"):
            os.system(f"umask 0077; wg genkey > out/{client}.key")
            os.system(f"umask 0077; wg genkey > out/{client}.psk")
            os.system(f"wg pubkey < out/{client}.key > out/{client}.pub")
        with open(f"out/{client}.key") as f:
            client_key = f.read().strip()
        with open(f"out/{client}.psk") as f:
            client_psk = f.read().strip()
        with open(f"out/{client}.conf", "w") as f:
            os.chmod(f.fileno(), 0o600)
            f.write(f'''\
[Interface]
PrivateKey = {client_key}
Address = {NETWORK[i]}/{NETWORK.prefixlen}

[Peer]
PublicKey = {server_pub}
PresharedKey = {client_psk}
AllowedIPs = 0.0.0.0/0
EndPoint = {host}:{PORT}
''')
        os.system(f'''umask 0077; command -v qrencode && qrencode -t png -o out/{client}.png < out/{client}.conf''')

WG_CONF = io.StringIO()

def generate_config(state, host):
    WG_CONF.write(f'''\
[Interface]
ListenPort = {PORT}
''')
    for i, client in enumerate(clients.CLIENTS, start=2):
        if client is None:
            continue
        with open(f"out/{client}.pub") as f:
            client_pub = f.read().strip()
        with open(f"out/{client}.psk") as f:
            client_psk = f.read().strip()
        WG_CONF.write(f'''\
[Peer]
PublicKey = {client_pub}
PresharedKey = {client_psk}
AllowedIPs = {NETWORK[i]}/{NETWORK[i].max_prefixlen}
''')

python.call(
    {'Generate client wireguard config'},
    generate_client_config,
)

python.call(
    {'Generate wireguard config'},
    generate_config,
)

files.put(
    {'Upload wireguard config'},
    WG_CONF,
    f'/etc/wireguard/{WG_IF}.conf',
)

files.put(
    {'Create wireguard interface configuration'},
    io.StringIO(f'''\
inet {SERVER} {NETWORK.netmask} NONE description "wireguard"
up

!/usr/local/bin/wg setconf {WG_IF} /etc/wireguard/wg0.conf
!/usr/local/bin/wg set {WG_IF} private-key /etc/wireguard/server.key
'''),
    f'/etc/hostname.{WG_IF}'
)

server.shell(
    {'Configure wireguard interface'},
    f'sh /etc/netstart ${WG_IF}'
)

server.shell(
    {'Enable IPv4 packet forwarding'},
    'sysctl net.inet.ip.forwarding=1'
)

files.line(
    {'Persist IPv4 packet forwarding'},
    '/etc/sysctl.conf',
    r'^net.inet.ip.forwarding=',
    replace='net.inet.ip.forwarding=1'
)

files.template(
    {'Generate PF config'},
    'templates/pf.conf.j2',
    '/etc/pf.conf',
    DEFAULT_IF=DEFAULT_IF,
    WG_IF=WG_IF,
)

server.shell(
    {'Enable PF'},
    'pfctl -f /etc/pf.conf; pfctl -e || true'
)
