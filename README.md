# Google Geocoding API を使ったCSV緯度経度付与ツール (Python)

住所を含むCSVに対して、Google Geocoding APIを使って緯度・経度を付与するスクリプトです。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Google APIキー

Google Cloudで Geocoding API を有効化し、APIキーを作成してください。

```bash
export GOOGLE_MAPS_API_KEY='YOUR_API_KEY'
```

## 使い方

```bash
python geocode_csv.py \
  サンプル_飲食店_豊中_緯度経度なし.csv \
  output_with_latlng.csv
```

オプション例:

```bash
python geocode_csv.py input.csv output.csv \
  --address-col 住所 \
  --lat-col 緯度 \
  --lng-col 経度 \
  --formatted-address-col 正規化住所 \
  --sleep 0.1 \
  --timeout 10
```

## 入出力

- 入力: 住所列（デフォルト列名: `住所`）
- 出力: `緯度`, `経度`, `正規化住所` を追記したCSV
- エンコーディング: UTF-8 with BOM (`utf-8-sig`)

## 注意点

- API利用料金・クォータ制限に注意してください。
- `OVER_QUERY_LIMIT` などで取得失敗した行は空欄になります。
- 同じ住所はプロセス内でキャッシュされ、重複API呼び出しを抑制します。
