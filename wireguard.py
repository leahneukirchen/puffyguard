import io
import ipaddress
import os
from pyinfra import host
from pyinfra.operations import files, pkg, python, server
from pyinfra.api.exceptions import OperationError
import ipfact

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

DEFAULT_IF = host.fact.command(
    '''route -n show -inet | awk '/^default/ { print $NF; exit }' ''')

ipv6nets = host.fact.ipv6_networks(DEFAULT_IF)
if ipv6nets:
    IPV6NETWORK = ipv6nets[0]
else:
    IPV6NETWORK = None

pkg.packages(
    name='Install wireguard tools',
    packages=['wireguard-tools'],
)

files.directory(
    name='Create wireguard configuration directory',
    path='/etc/wireguard',
    user='root', group='wheel', mode='600'
)

server.shell(
    name='Generate server keys',
    commands=['''
    if ! test -f /etc/wireguard/server.key; then (
      umask 0077
      wg genkey > /etc/wireguard/server.key
      wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub
    ); fi
    ''']
)

files.get(
    name='Retrieve server public key',
    src='/etc/wireguard/server.pub',
    dest='out/server.pub'
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
            addresses = [ f"{NETWORK[i]}/{NETWORK.prefixlen}" ]
            if IPV6NETWORK:
                addresses.append(f"{IPV6NETWORK[102*16*16*16*16 + i]}/{IPV6NETWORK.prefixlen}")
            f.write(f'''\
[Interface]
PrivateKey = {client_key}
Address = {', '.join(addresses)}

[Peer]
PublicKey = {server_pub}
PresharedKey = {client_psk}
AllowedIPs = 0.0.0.0/0{ ", ::/0" if IPV6NETWORK else "" }
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
        addresses = [ f"{NETWORK[i]}/{NETWORK.max_prefixlen}" ]
        if IPV6NETWORK:
            addresses.append(f"{IPV6NETWORK[102*16*16*16*16 + i]}/{IPV6NETWORK.max_prefixlen}")
        WG_CONF.write(f'''\
[Peer]
PublicKey = {client_pub}
PresharedKey = {client_psk}
AllowedIPs = {', '.join(addresses)}
''')

python.call(
    name='Generate client wireguard config',
    function=generate_client_config,
)

python.call(
    name='Generate wireguard config',
    function=generate_config,
)

files.put(
    name='Upload wireguard config',
    src=WG_CONF,
    dest=f'/etc/wireguard/{WG_IF}.conf',
)

files.put(
    name='Create wireguard interface configuration',
    src=io.StringIO(f'''\
inet {SERVER} {NETWORK.netmask} NONE description "wireguard"
{f"inet6 alias {IPV6NETWORK[102*16*16*16*16]}/112" if IPV6NETWORK else ""}
up

!/usr/local/bin/wg setconf {WG_IF} /etc/wireguard/wg0.conf
!/usr/local/bin/wg set {WG_IF} private-key /etc/wireguard/server.key
'''),
    dest=f'/etc/hostname.{WG_IF}',
    mode='640'
)

server.shell(
    name='Configure wireguard interface',
    commands=[f'sh /etc/netstart ${WG_IF}'],
)

server.shell(
    name='Enable IPv4 packet forwarding',
    commands=['sysctl net.inet.ip.forwarding=1'],
)

files.line(
    name='Persist IPv4 packet forwarding',
    path='/etc/sysctl.conf',
    line=r'^net.inet.ip.forwarding=',
    replace='net.inet.ip.forwarding=1',
)

if IPV6NETWORK:
    server.shell(
        name='Enable IPv6 packet forwarding',
        commands=['sysctl net.inet6.ip6.forwarding=1'],
    )

    files.line(
        name='Persist IPv4 packet forwarding',
        path='/etc/sysctl.conf',
        line=r'^net.inet6.ip6.forwarding=',
        replace='net.inet6.ip6.forwarding=1',
    )

files.template(
    name='Generate PF config',
    src='templates/pf.conf.j2',
    dest='/etc/pf.conf',
    mode='600',
    DEFAULT_IF=DEFAULT_IF,
    WG_IF=WG_IF,
    IPV6NETWORK=IPV6NETWORK,
)

server.shell(
    name='Enable PF',
    commands=['pfctl -f /etc/pf.conf; pfctl -e || true'],
)
