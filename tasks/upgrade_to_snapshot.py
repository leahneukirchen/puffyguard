from pyinfra import host
from pyinfra.operations import server

server.shell(
    name='Upgrade to latest snapshot',
    commands=['sysupgrade -s -n'],
)

server.reboot(
    name='Reboot the server and wait to reconnect',
    delay=5,
    timeout=30,
    reboot_timeout=10*60,
)

server.shell(
    name='Upgrade all packages',
    commands=['pkg_add -u'],
)
