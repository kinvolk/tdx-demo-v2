#!/bin/bash

set -euo pipefail

export KEY=$(curl -sf http://localhost:8006/cdh/resource/default/key/secretkey)
python3 count_words.py

sleep infinity
