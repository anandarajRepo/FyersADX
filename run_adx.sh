#!/bin/bash
truncate -s 0 /var/log/adx.log
truncate -s 0 cd /root/FyersADX/adx.log
cd /root/FyersADX
source venv/bin/activate
python3.11 -u main.py run --paper 2>&1 | tee -a adx.log