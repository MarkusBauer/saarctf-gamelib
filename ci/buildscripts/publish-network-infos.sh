#!/usr/bin/env bash

set -eu

echo 'Container start at' "$(date)"
echo 'Bound IP addresses:' > /tmp/machine-infos.txt
ip addr | egrep -o 'inet [0-9]+\.[0-9]+\.[0-9]+\.[0-9]' >> /tmp/machine-infos.txt
cat /tmp/machine-infos.txt
