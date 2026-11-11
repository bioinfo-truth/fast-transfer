#!/bin/sh
umask 077
ulimit -c 0
exec /home/drwho1985/.local/lib/fast-transfer/baidupcs-go-v4.0.2-native-20261111/BaiduPCS-Go "$@"
