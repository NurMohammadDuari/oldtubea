#!/bin/bash
cd "$(dirname "$0")"
./cloudflared tunnel --url http://localhost:8081 --no-autoupdate
