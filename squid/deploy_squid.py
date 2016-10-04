#!/usr/bin/env python

# Copyright (c) 2014, Tully Foote

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


import os
import subprocess
import socket
import sys
import time
import re
import base64

prepare_cache_cmd = "chown -R proxy:proxy /var/cache/squid3"
build_cmd = "squid3 -z"
squid_cmd = "squid3 -N"

def hide_password(conf):
    return re.sub("login=\s*([^\r]*)", "login=*****", conf)

def main():
    if os.geteuid() != 0:
        print("This must be run as root, aborting")
        return -1

    # clean up any stale pid files
    if os.path.exists("/run/squid3.pid"):
        os.remove("/run/squid3.pid")

    max_object_size = os.getenv("MAXIMUM_CACHE_OBJECT", '1024')
    disk_cache_size = os.getenv("DISK_CACHE_SIZE", '5000')
    squid_directives_only = os.getenv("SQUID_DIRECTIVES_ONLY", False)
    arbitrary_squid_directives = os.getenv("SQUID_DIRECTIVES", None)

    squid_conf_entries = []
    squid_conf_entries.append('http_port 0.0.0.0:3129 intercept')
    squid_conf_entries.append('maximum_object_size %s MB' % max_object_size)
    squid_conf_entries.append('cache_dir ufs /var/cache/squid3 %s 16 256' %
                              disk_cache_size)
    # Configure upstream proxy
    pp_host = os.getenv("PARENT_PROXY_HOST", None)
    if pp_host is not None:
        pp_port = os.getenv("PARENT_PROXY_PORT")

        pp_username = os.getenv("PARENT_PROXY_USERNAME", None)
        if pp_username is not None:
            # base64 decode password to avoid shoulder surfers
            pp_password = base64.b64decode(os.getenv("PARENT_PROXY_PASSWORD"))
            squid_conf_entries.append('cache_peer %s parent %s 0 no-query no-digest login=%s:%s' % (pp_host, pp_port, pp_username, pp_password))
        else:
            squid_conf_entries.append('cache_peer %s parent %s 0 no-query no-digest' % (pp_host, pp_port))
        squid_conf_entries.append('never_direct allow all')

    with open("/etc/squid3/squid.conf", 'w') as conf_fh:

        if not squid_directives_only:
            with open("/etc/squid3/squid.conf.in", "r") as preconf:
                conf_fh.write(preconf.read())
            for conf in squid_conf_entries:
                print("Appending to squid.conf: [%s]" % hide_password(conf))
                conf_fh.write(conf + '\n')

        if arbitrary_squid_directives:
            print("Appending squid directives to squid.conf")
            print(arbitrary_squid_directives)
            conf_fh.write(arbitrary_squid_directives)

    # Setup squid directories
    # Reassert permissions in case of mounting from outside
    subprocess.check_call(prepare_cache_cmd, shell=True)
    subprocess.check_call(build_cmd, shell=True)

    # wait for the above non-blockin call to finish setting up the directories
    time.sleep(5)

    # Start the squid instance as a subprocess
    squid_in_a_can = subprocess.Popen(squid_cmd, shell=True)

    # While the process is running wait for squid to be running
    print("Waiting for squid to finish")
    while squid_in_a_can.poll() is None:
        time.sleep(1)

    print("Squid process exited with return code %s" %
          squid_in_a_can.returncode)
    return squid_in_a_can.returncode

if __name__ == '__main__':
    sys.exit(main())
