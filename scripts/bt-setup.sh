#!/bin/bash
# Bluetooth 自動セットアップスクリプト
# RPi 起動時に discoverable / pairable 状態にする

set -euo pipefail

LOG_TAG="bt-setup"

log() {
    logger -t "$LOG_TAG" "$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Bluetooth セットアップを開始"

# Bluetooth ブロック解除
rfkill unblock bluetooth
log "rfkill unblock bluetooth 完了"

# HCI デバイスを起動
hciconfig hci0 up
log "hciconfig hci0 up 完了"

# bluetoothctl で discoverable / pairable に設定
bluetoothctl <<EOF
power on
discoverable on
pairable on
agent NoInputNoOutput
default-agent
EOF

log "bluetoothctl 設定完了 (discoverable on, pairable on)"

# discoverable を維持するため、タイムアウトを無効化
bluetoothctl discoverable-timeout 0
log "discoverable-timeout を 0（無制限）に設定"

log "Bluetooth セットアップ完了"
