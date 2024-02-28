#!/bin/bash

cd /home/$USER
mkdir -p .jupyter
cd .jupyter
openssl req -x509 -nodes -days 10000 -newkey rsa:2048 -keyout mykey.key -out mycert.pem
if [ ! -f jupyter_notebook_config.py ]; then
    jupyter notebook --generate-config
fi
hashed_pass=`python -c "from __future__ import print_function; from jupyter_server.auth import passwd; res = passwd(); print(res)"`

cat <<EOF > jupyter_notebook_config.py
c.ServerApp.certfile = '/home/$USER/.jupyter/mycert.pem'
c.ServerApp.keyfile = '/home/$USER/.jupyter/mykey.key'
c.ServerApp.open_browser = False
c.ServerApp.ip = '*'
c.ServerApp.port = $UID
c.ServerApp.password = '$hashed_pass'
EOF