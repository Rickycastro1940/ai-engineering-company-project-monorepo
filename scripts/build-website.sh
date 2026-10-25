#!/bin/sh
set -eu
rm -rf dist
mkdir dist
cp -a uis/website-classic/. dist
rm -f dist/README.md
echo "Published classic Brasaland site ($(find dist -type f | wc -l) files)"
