from pyinfra import host
from pyinfra.operations import server

server.shell(
    {'Upgrade to latest snapshot'},
    'sysupgrade -s -n',
)

server.reboot(
    {'Reboot the server and wait to reconnect'},
    delay=5,
    timeout=30,
    reboot_timeout=10*60
)

server.shell(
    {'Upgrade all packages'},
    'pkg_add -u'
)
