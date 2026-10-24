#!/bin/sh
set -eu
echo "Node $(node -v)"
npm ci --include=dev --prefix uis/website
npm run build --prefix uis/website
rm -rf dist
cp -a uis/website/dist dist
