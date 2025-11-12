#!/bin/sh
# shellcheck shell=sh

if [ -z "$husky_skip_init" ]; then
  husky_skip_init=1
  export husky_skip_init
  . "$(dirname "$0")/../../node_modules/husky/husky.sh"
fi
