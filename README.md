# Google Geocoding API を使ったCSV緯度経度付与ツール (Python)

住所を含むCSVに対して、Google Geocoding APIを使って緯度・経度を付与するスクリプトです。

## Google Colab で実行する（ローカル環境不要）

ローカル環境がなくても、Colab ノートブック `geocode_colab.ipynb` を開けば実行できます。

### 手順

1. このリポジトリを GitHub に置く（または既存の GitHub リポジトリを使う）
2. Colab で `geocode_colab.ipynb` を開く
3. ノートブック内の手順で API キーを設定し、CSV をアップロードして実行
4. 出力 CSV を Colab からダウンロード

> 補足: `geocode_csv.py` は標準ライブラリのみで動作するため、Colab 上でも追加インストール不要です。

## ローカルで実行する場合（任意）

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
  --name-col 店の名前 \
  --lat-col 緯度 \
  --lng-col 経度 \
  --formatted-address-col 正規化住所 \
  --places-bias-radius 3000 \
  --sleep 0.1 \
  --timeout 10
```

Places APIを使わず住所Geocodingのみにしたい場合:

```bash
python geocode_csv.py input.csv output.csv --disable-places
```

## 入出力

- 入力: 住所列（デフォルト列名: `住所`）
- 出力: `緯度`, `経度`, `正規化住所` に加えて、`採用方式`, `信頼度`, `place_id`, `候補スコア`, `フォールバック理由` などを追記したCSV
- エンコーディング: UTF-8 with BOM (`utf-8-sig`)

### geocode_fallback 行を対話レビューして最終CSVを作る

`geocode_csv.py` 実行後に、`LOW_PLACE_CONFIDENCE` でフォールバックした行だけを1件ずつ確認し、
`geocode` のままにするか `places` 候補を採用するかを選べます。

```bash
python review_fallbacks.py geocode_result.csv finalized.csv
```

- 対象: `採用方式=geocode_fallback` かつ `フォールバック理由=LOW_PLACE_CONFIDENCE:*`
- 入力操作:
  - `p`: Places候補を採用
  - `g`: Geocodeのまま維持
  - `q`: 途中で保存して終了
- Places採用時は `採用方式=places_manual_review`, `信頼度=manual_override` に更新

### Colab上の一括自動採用セル（`places_auto_review`）

`geocode_colab.ipynb` には、対話レビューの前に以下の自動判定セルを追加しています。

- 対象: `採用方式=geocode_fallback` かつ `フォールバック理由=LOW_PLACE_CONFIDENCE:*`
- 条件: `places_geocode_distance_m <= 50`
- 処理: Places候補を一括採用し、`採用方式=places_auto_review` として保存

このセルは `FINAL_OUTPUT_CSV` を更新するため、続けて対話レビューセルを実行すると、
残りの曖昧な行だけを `p/g` で確認できます。


#### Colabランタイムを切らずに、既存セルへ直接貼り付ける用コード

以下をそのまま **新規セル** または **既存セルの差し替え** に貼り付けて実行できます。

```python
import csv
from pathlib import Path

AUTO_REVIEW_ENABLED = True
AUTO_REVIEW_MAX_DISTANCE_M = 50.0

if not AUTO_REVIEW_ENABLED:
    print('一括自動採用をスキップしました。')
else:
    in_path = Path(OUTPUT_CSV)
    out_path = Path(FINAL_OUTPUT_CSV)

    if not in_path.exists():
        raise FileNotFoundError(f'入力CSVが見つかりません: {in_path}')

    source_path = out_path if out_path.exists() else in_path
    with source_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = list(reader)

    required_cols = [
        '採用方式', 'フォールバック理由', '緯度', '経度',
        '正規化住所', '候補住所(採用)', '候補緯度(採用)', '候補経度(採用)',
        'places_geocode_distance_m'
    ]
    for col in required_cols:
        if col not in headers:
            raise ValueError(f'必要列がありません: {col}')

    changed = 0
    for row in rows:
        method = (row.get('採用方式', '') or '').strip()
        reason = (row.get('フォールバック理由', '') or '').strip()
        if method not in {'geocode_fallback', 'places_auto_review'}:
            continue
        if not reason.startswith('LOW_PLACE_CONFIDENCE:'):
            continue

        cand_lat = (row.get('候補緯度(採用)') or '').strip()
        cand_lng = (row.get('候補経度(採用)') or '').strip()
        if not cand_lat or not cand_lng:
            continue

        try:
            distance_m = float((row.get('places_geocode_distance_m') or '').strip())
        except ValueError:
            continue

        if distance_m <= AUTO_REVIEW_MAX_DISTANCE_M:
            row['緯度'] = cand_lat
            row['経度'] = cand_lng
            row['正規化住所'] = row.get('候補住所(採用)', '')
            row['採用方式'] = 'places_auto_review'
            row['信頼度'] = 'auto_override'
            row['フォールバック理由'] = f'AUTO_PLACE_OVERRIDE:distance_le_{int(AUTO_REVIEW_MAX_DISTANCE_M)}m'
            changed += 1

    with out_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    print(f'一括採用件数: {changed}件 (閾値: {AUTO_REVIEW_MAX_DISTANCE_M}m)')
    print(f'保存先: {out_path}')
```

> 補足: 後工程での人手判断ができるよう、`geocode_csv.py` は `候補緯度(採用)` / `候補経度(採用)` も出力します。

### Colabでの同期について（新しい `.py` が増えた場合）

- はい、手動アップロード運用の場合は、追加した `.py` も都度同期が必要です。
- ただし `geocode_colab.ipynb` の GitHub 同期（`git clone`）を使えば、**リポジトリ全体を取得**するため追加 `.py` の個別同期は不要です。
- さらに、Notebook内に `LOW_PLACE_CONFIDENCE` 行を対話レビューして最終CSVを作るセルを追加しているため、
  `review_fallbacks.py` を直接実行しなくても Colab 上で同じ運用ができます。

### 全体ルールの保存場所

- 全体運用ルールは `WORKFLOW_RULES.md` に記載しています。
- ルール変更時は `README.md` / `geocode_colab.ipynb` / `WORKFLOW_RULES.md` を同時更新してください。

## 注意点

- API利用料金・クォータ制限に注意してください。
- `OVER_QUERY_LIMIT` などで取得失敗した行は空欄になります。
- 同じ住所はプロセス内でキャッシュされ、重複API呼び出しを抑制します。

## よくあるズレと改善方法（住所とGoogleマップ表示位置が少し違う）

`formatted_address`（正規化住所）は、Googleが返す「代表的な住所表記」です。表記が短くなることがあり、
例として `大阪府豊中市旭丘5-105` が `大阪府豊中市旭丘５` のように見えるケースがあります。
これは「住所文字列の表示が変わった」だけで、必ずしも座標自体が誤りとは限りません。

ただし、店舗の実際のピン位置に寄せたい場合、住所だけの Geocoding では限界があります。
特に以下のケースでズレやすくなります。

- 建物名・号室・枝番が欠落している
- 住所より店舗名のほうが Google マップ上で強く認識される
- 施設の入口や代表点（道路・街区中心）が返る

精度を上げる実務上の方法は次の通りです。

1. **店舗名 + 住所で検索する**
   - Geocoding の `address` に店舗名を足す（例: `キャコタ 大阪府豊中市旭丘5-105`）
   - 住所単体より、実在店舗の候補に寄りやすくなります。
2. **Places API（Text Search / Find Place）を併用する**
   - 「Google マップで店名検索した結果」に近いロジックで座標を取得できます。
   - 候補が複数ある場合は、住所一致度や電話番号などで絞り込みます。
3. **結果の品質判定を保存する**
   - Geocoding の `geometry.location_type`（`ROOFTOP` / `RANGE_INTERPOLATED` など）を保存し、
     精度が低い行だけ再検索します。
4. **最終的に人手確認の対象を限定する**
   - 「店名検索結果と住所検索結果の距離が一定以上」の行のみレビューする運用が現実的です。

結論として、**「Googleマップで店名検索したときと同じ場所」を狙うなら、住所ジオコーディング単独では不十分で、
店名ベース（Places API）との併用が有効**です。


## 実装フロー例（店舗名ゆらぎ・同名店舗が多い場合）

ご提案の ①〜③ は妥当です。さらに精度と運用性を上げるなら、**段階的フォールバック + スコア判定**にすると安定します。

### 推奨フロー（改善版）

1. **入力の前処理**
   - 店舗名: 記号・全半角・法人格（例: 株式会社）・支店接尾辞を正規化
   - 住所: 既存どおり正規化
   - 郵便番号: 7桁の数字に正規化
2. **Places 検索（第一候補）**
   - クエリは `店舗名 + 市区町村 + 郵便番号(あれば)`
   - `locationbias`（円/矩形）を使って対象エリアへ寄せる
   - 取得項目: `place_id`, `name`, `formatted_address`, `geometry/location`, `types`
3. **候補スコアリング**
   - `name` 類似度（N-gram/編集距離）
   - 郵便番号一致（完全一致を高加点）
   - 住所要素一致（都道府県/市区町村/町域）
   - 元住所ジオコード点との距離（近いほど加点）
   - `types` が `restaurant` など業態整合なら加点
4. **自動採用条件**
   - 最高スコアが閾値以上、かつ 2位との差が十分あるときのみ自動確定
   - 確定時は `place_id` を保存（再現性のため）
5. **曖昧時のフォールバック**
   - 候補なし/低信頼: 住所 Geocoding にフォールバック
   - 出力に `match_method`（`places` / `geocode_fallback`）と `confidence`（high/medium/low）を記録
6. **レビュー対象の最小化**
   - `confidence=low` と「Places点とGeocode点の距離が閾値超過」の行だけ人手確認

### ご提案フローへのコメント

- ① **良いです**。店舗名単体より、郵便番号・市区町村・`locationbias` を加えるのが有効です。
- ②-1 **良いです**。郵便番号一致は強い指標ですが、欠損や誤記もあるため「一致しない=即不採用」ではなく減点扱いが安全です。
- ③-1 **良いです**。加えて `place_id` と `match_score` を保存すると、後から検証しやすくなります。
- ②-2/③-2 **妥当です**。`geocode_fallback` と理由（`NO_PLACE_CANDIDATE` など）を列で残すと運用しやすくなります。

### 追加すると実務で効く出力列

- `採用方式`（places/geocode_fallback）
- `信頼度`（high/medium/low）
- `place_id`
- `候補店名(採用)`
- `候補住所(採用)`
- `候補スコア`
- `フォールバック理由`
- `places_geocode_distance_m`

この形にすると、精度とトレーサビリティを両立できます。
