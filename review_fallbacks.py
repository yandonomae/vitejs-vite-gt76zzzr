#!/usr/bin/env python3
import argparse
import csv
from typing import List, Tuple


def _read_rows(path: str) -> Tuple[List[str], List[dict]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSVヘッダーが見つかりません")
        return list(reader.fieldnames), list(reader)


def _write_rows(path: str, headers: List[str], rows: List[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _is_review_target(row: dict, match_method_col: str, fallback_reason_col: str) -> bool:
    method = (row.get(match_method_col) or "").strip()
    reason = (row.get(fallback_reason_col) or "").strip()
    return method == "geocode_fallback" and reason.startswith("LOW_PLACE_CONFIDENCE:")


def _can_apply_place(row: dict, matched_lat_col: str, matched_lng_col: str) -> bool:
    return bool((row.get(matched_lat_col) or "").strip() and (row.get(matched_lng_col) or "").strip())


def interactive_review(
    input_csv: str,
    output_csv: str,
    address_col: str,
    name_col: str,
    lat_col: str,
    lng_col: str,
    formatted_address_col: str,
    match_method_col: str,
    confidence_col: str,
    fallback_reason_col: str,
    matched_name_col: str,
    matched_address_col: str,
    matched_lat_col: str,
    matched_lng_col: str,
    match_score_col: str,
    distance_col: str,
) -> None:
    headers, rows = _read_rows(input_csv)

    targets = [i for i, row in enumerate(rows) if _is_review_target(row, match_method_col, fallback_reason_col)]
    print(f"review対象: {len(targets)}件")
    if not targets:
        _write_rows(output_csv, headers, rows)
        print(f"対象がないため、そのまま出力しました: {output_csv}")
        return

    for n, idx in enumerate(targets, start=1):
        row = rows[idx]
        print("\n" + "=" * 70)
        print(f"[{n}/{len(targets)}] 行番号(ヘッダー除く): {idx + 2}")
        print(f"店名: {row.get(name_col, '')}")
        print(f"住所: {row.get(address_col, '')}")
        print(f"現在採用(geocode): ({row.get(lat_col, '')}, {row.get(lng_col, '')}) / {row.get(formatted_address_col, '')}")
        print(f"候補(places): {row.get(matched_name_col, '')}")
        print(f"候補住所: {row.get(matched_address_col, '')}")
        print(f"候補座標: ({row.get(matched_lat_col, '')}, {row.get(matched_lng_col, '')})")
        print(f"候補スコア: {row.get(match_score_col, '')} / 距離m: {row.get(distance_col, '')}")
        print(f"フォールバック理由: {row.get(fallback_reason_col, '')}")

        if not _can_apply_place(row, matched_lat_col, matched_lng_col):
            print("候補座標がないため、この行はgeocode維持します。")
            continue

        while True:
            cmd = input("選択 [p=places採用 / g=geocode維持 / q=終了して保存]: ").strip().lower()
            if cmd == "p":
                row[lat_col] = row.get(matched_lat_col, "")
                row[lng_col] = row.get(matched_lng_col, "")
                row[formatted_address_col] = row.get(matched_address_col, "")
                row[match_method_col] = "places_manual_review"
                row[confidence_col] = "manual_override"
                row[fallback_reason_col] = "MANUAL_PLACE_OVERRIDE"
                print("→ Placesを採用しました")
                break
            if cmd == "g":
                print("→ Geocodeのまま維持しました")
                break
            if cmd == "q":
                _write_rows(output_csv, headers, rows)
                print(f"途中保存しました: {output_csv}")
                return
            print("無効な入力です。p / g / q を入力してください。")

    _write_rows(output_csv, headers, rows)
    print(f"レビュー結果を保存しました: {output_csv}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="geocode_fallback(LOW_PLACE_CONFIDENCE)行を対話で見直してCSVを確定")
    p.add_argument("input_csv")
    p.add_argument("output_csv")
    p.add_argument("--address-col", default="住所")
    p.add_argument("--name-col", default="店の名前")
    p.add_argument("--lat-col", default="緯度")
    p.add_argument("--lng-col", default="経度")
    p.add_argument("--formatted-address-col", default="正規化住所")
    p.add_argument("--match-method-col", default="採用方式")
    p.add_argument("--confidence-col", default="信頼度")
    p.add_argument("--fallback-reason-col", default="フォールバック理由")
    p.add_argument("--matched-name-col", default="候補店名(採用)")
    p.add_argument("--matched-address-col", default="候補住所(採用)")
    p.add_argument("--matched-lat-col", default="候補緯度(採用)")
    p.add_argument("--matched-lng-col", default="候補経度(採用)")
    p.add_argument("--match-score-col", default="候補スコア")
    p.add_argument("--distance-col", default="places_geocode_distance_m")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    interactive_review(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        address_col=args.address_col,
        name_col=args.name_col,
        lat_col=args.lat_col,
        lng_col=args.lng_col,
        formatted_address_col=args.formatted_address_col,
        match_method_col=args.match_method_col,
        confidence_col=args.confidence_col,
        fallback_reason_col=args.fallback_reason_col,
        matched_name_col=args.matched_name_col,
        matched_address_col=args.matched_address_col,
        matched_lat_col=args.matched_lat_col,
        matched_lng_col=args.matched_lng_col,
        match_score_col=args.match_score_col,
        distance_col=args.distance_col,
    )
