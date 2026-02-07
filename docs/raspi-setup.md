# Raspberry Pi セットアップ手順

BT Metadata Collector を Raspberry Pi 4 で動作させるためのセットアップ手順。

## 1. OS インストール

### 1.1 準備するもの

- Raspberry Pi 4 Model B（2GB 以上）
- microSD カード（16GB 以上推奨）
- セットアップ用の Mac / PC
- 電源アダプタ（USB-C, 5V/3A）

### 1.2 Raspberry Pi Imager で書き込み

1. [Raspberry Pi Imager](https://www.raspberrypi.com/software/) をダウンロード・インストール
2. microSD カードを PC に挿入
3. Imager を起動し、以下を設定:
   - **デバイス**: Raspberry Pi 4
   - **OS**: Raspberry Pi OS (64-bit) Bookworm — **Lite**（Desktop なし）で十分
   - **ストレージ**: 挿入した microSD カード
4. **設定の編集**（歯車アイコン）で以下を入力:
   - **一般設定**:
     - ホスト名: `bt-collector`（任意）
     - ユーザー名: `pi` / パスワード: `********`
     - Wi-Fi: SSID とパスワードを入力（記録用 Mac と同じネットワーク）
     - ロケール: Asia/Tokyo, JP キーボード
   - **サービス設定**:
     - SSH を有効化する（パスワード認証）
5. 書き込みを実行（20〜30 分程度）

> 参考: https://sukiburo.jp/setup-raspberry-pi/

### 1.3 初回起動

1. microSD カードを Raspberry Pi に挿入
2. 電源を接続（約 1 分で起動完了）
3. Mac のターミナルから SSH 接続を確認:

```bash
# ホスト名で接続
ssh pi@bt-collector.local

# またはIPアドレスで接続（ping で確認）
ping bt-collector.local
ssh pi@<表示されたIPアドレス>
```

---

## 2. システム更新と依存パッケージ

SSH 接続後、以下を実行:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    bluez \
    python3-venv python3-dev python3-dbus python3-gi \
    libdbus-1-dev libglib2.0-dev pkg-config gcc \
    git
```

> **注意**: PipeWire / PulseAudio は **不要**。本ツールはオーディオ再生せず、AVRCP メタデータのみを取得する。A2DP Sink プロファイルの登録は BlueZ が自動で行う。

---

## 3. Bluetooth 設定

### 3.1 BlueZ 設定ファイルの編集

```bash
sudo nano /etc/bluetooth/main.conf
```

`[General]` セクションに以下を追記:

```ini
[General]
Name = BT-MetadataCollector
Class = 0x20041C
DiscoverableTimeout = 0
AlwaysPairable = true
JustWorksRepairing = always
```

設定を反映:

```bash
sudo systemctl restart bluetooth
```

### 3.2 ペアリング手順（端末ごと）

```bash
bluetoothctl
```

`bluetoothctl` 内で以下を実行:

```
discoverable on
pairable on
agent on
default-agent
```

この状態で、コンテンツ再生端末（iPhone / Mac / Windows / Android）の Bluetooth 設定画面から **「BT-MetadataCollector」** を検出してペアリングする。

ペアリング完了後、`bluetoothctl` で trust を実行して自動再接続を有効化:

```
trust XX:XX:XX:XX:XX:XX
```

> `XX:XX:XX:XX:XX:XX` はペアリングした端末の MAC アドレスに置き換える。

```
exit
```

**全対象端末（iPhone / Mac / Windows / Android）で上記を実施する。**

---

## 4. アプリケーションのデプロイ

```bash
cd ~
git clone <リポジトリURL> bt-metadata-collector
cd bt-metadata-collector
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p data
```

> `--system-site-packages` は `dbus-python` と `PyGObject` をシステムパッケージから引き込むために必要。

---

## 5. 動作確認

### モックモードで確認

```bash
source .venv/bin/activate
BT_MOCK=true uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Mac のブラウザで `http://bt-collector.local:8000` にアクセスして動作確認。

### 実機モードで確認

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 6. systemd サービス登録

自動起動を設定する:

```bash
sudo cp bt-metadata-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bt-metadata-collector
sudo systemctl start bt-metadata-collector
```

ステータス確認:

```bash
sudo systemctl status bt-metadata-collector
```

ログ確認:

```bash
journalctl -u bt-metadata-collector -f
```

---

## 7. IP アドレスの固定（推奨）

安定した接続のために、Raspberry Pi の IP アドレスを固定することを推奨:

```bash
sudo nano /etc/dhcpcd.conf
```

ファイル末尾に以下を追記（ネットワーク環境に合わせて変更）:

```
interface wlan0
static ip_address=192.168.0.100/24
static routers=192.168.0.1
static domain_name_servers=192.168.0.1 8.8.8.8
```

```bash
sudo reboot
```

再起動後、固定した IP アドレスで SSH 接続・ブラウザアクセスが可能。

---

## 8. 出先での利用（iPhone テザリング）

自宅以外の場所で使う場合、iPhone のテザリングを利用できる。

### 事前準備（自宅で SSH 接続した状態で実行）

iPhone のテザリングネットワークを RPi に登録しておく:

```bash
sudo nmcli dev wifi connect "iPhoneの名前" password "テザリングのパスワード"
```

> - iPhone の名前: **設定 → 一般 → 情報 → 名前** で確認
> - テザリングのパスワード: **設定 → インターネット共有** で確認

一度登録すれば、RPi は電源投入時に見つかった Wi-Fi へ自動接続する。

### 出先での使い方

1. iPhone で **インターネット共有** をオンにする
2. Raspberry Pi の電源を入れる → iPhone テザリングに自動接続
3. Mac も同じ iPhone テザリングに接続する
4. Mac のブラウザで `http://bt-collector.local:8000` にアクセス
