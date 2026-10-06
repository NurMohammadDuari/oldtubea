#!/bin/bash
# downloads cloudflared for this PC
arch=$(uname -m)
if [ "$arch" = "x86_64" ]; then url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64";
else url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"; fi
curl -L -o cloudflared "$url" && chmod +x cloudflared && ./cloudflared --version
