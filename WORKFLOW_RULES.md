# Workflow Rules (運用ルール)

このリポジトリを使うときは、毎回このファイルを最初に確認してください。

## 1. 同期ルール
- Colabでは原則GitHubからリポジトリを同期して実行する。
- `geocode_csv.py` 以外に新しいモジュール（例: `review_fallbacks.py`）が増えた場合も、同期対象は**リポジトリ全体**なので追加操作は不要。
- 手動アップロード運用をする場合は、必要ファイルの不足が起きやすいため非推奨。

## 2. 出力確定ルール
- まず `geocode_csv.py` で一括処理した中間CSVを作る。
- Notebook運用では、必要に応じて `LOW_PLACE_CONFIDENCE` かつ `places_geocode_distance_m <= 50` を自動で `places_auto_review` 採用してよい。
- `採用方式=geocode_fallback` かつ `フォールバック理由=LOW_PLACE_CONFIDENCE:*` の行だけをレビュー対象にする。
- 最終CSVは、レビュー判断（geocode維持 / places採用）を反映したものを採用する。

## 3. 変更時の整合性ルール
- 新しい列や新しい判定フローを追加したら、以下を必ず同時更新する。
  1. `README.md`（運用手順）
  2. `geocode_colab.ipynb`（Colab実行手順）
  3. この `WORKFLOW_RULES.md`（全体ルール）
- 既存列名を変える場合、CLIオプションのデフォルト値とNotebook内の列参照も合わせて更新する。

## 4. Notebook優先ルール
- Colab利用者向けには、Notebook単体で完結できる操作（実行・レビュー・ダウンロード）を提供する。
- 補助CLIは残してよいが、Notebookにも同等のレビュー導線を用意する。
