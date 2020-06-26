# PuffyGuard

PuffyGuard provides a low-effort way to automatically deploy OpenBSD
machines serving as [WireGuard](https://www.wireguard.com/) endpoints using
[pyinfra](https://github.com/Fizzadar/pyinfra).

## Disclaimer

The author has a rough idea how WireGuard and OpenBSD work,
and never used `pyinfra` or `pf` before.
Please audit before serious use!

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER 
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Requirements on the deploying machine

* Python 3

* pyinfra 0.15 or a pipenv:
  ```
  pipenv lock
  pipenv sync
  ```

* wireguard-tools

* qrencode (optional)

## Requirements on the target machine

* Clean install of OpenBSD 6.7.
  * I use a pre-installed 1024MB instance at Vultr ($5 / month).
* Login as `root` is possible without entering a password (using SSH keys).

## Setting up PuffyGuard

* Add the VM to the `inventory.py`:
  ```
  my_hosts = [ ('192.0.2.2', {'ssh_user': 'root'}) ]
  ```

* Configure the names of the WireGuard clients in `clients.py`.

* Migrate to a OpenBSD 6.7-current snapshot (takes a few minutes):
  ```
  pipenv run pyinfra -vv inventory.py tasks/upgrade_to_snapshot.py
  ```

  This step is only needed once (or if you want to upgrade the snapshot).

* Generate and deploy the WireGuard configuration.
  ```
  pipenv run pyinfra -vv inventory.py wireguard.py
  ```

* Launch WireGuard on your client:
  * Copy the `out/$client.conf` to `/etc/wireguard/$client.conf`
    and run `wg-quick up $client`.
  * Scan `out/$client.png` with the WireGuard app on smartphone.

  The default configuration tunnels all IPv4 traffic through WireGuard,
  adjust `AllowedIPs` to your taste.

* To generate new accounts, just append them to `clients.py`
  and redeploy `wireguard.py`.

* To regenerate keys, delete `out/$client.key` and redeploy.

* To delete accounts, replace the name by None, else all IPs will shift;
  then redeploy.

## Author

Created by Leah Neukirchen <leah@vuxu.org>
as a Mayflower Mayday project on 2020-06-26.

To the extent possible under law, the creator of this work has waived
all copyright and related or neighboring rights to this work.

http://creativecommons.org/publicdomain/zero/1.0/
