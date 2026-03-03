#!/usr/bin/env python3
"""CSVの住所列をGoogle Geocoding APIで緯度経度に変換するスクリプト。"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    formatted_address: str


class GoogleGeocoder:
    def __init__(self, api_key: str, sleep_seconds: float = 0.1, timeout_seconds: int = 10) -> None:
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: Dict[str, Optional[GeocodeResult]] = {}

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        address = address.strip()
        if not address:
            return None

        if address in self._cache:
            return self._cache[address]

        params = urllib.parse.urlencode(
            {"address": address, "key": self.api_key, "language": "ja", "region": "jp"}
        )
        url = f"{GEOCODE_URL}?{params}"
        req = urllib.request.Request(url=url, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"APIリクエスト失敗: address='{address}', error={exc}") from exc

        status = payload.get("status")
        if status == "OK":
            top = payload["results"][0]
            loc = top["geometry"]["location"]
            result = GeocodeResult(
                lat=loc["lat"],
                lng=loc["lng"],
                formatted_address=top.get("formatted_address", ""),
            )
            self._cache[address] = result
            time.sleep(self.sleep_seconds)
            return result

        if status in {"ZERO_RESULTS", "OVER_DAILY_LIMIT", "OVER_QUERY_LIMIT", "REQUEST_DENIED", "INVALID_REQUEST"}:
            self._cache[address] = None
            time.sleep(self.sleep_seconds)
            return None

        raise RuntimeError(f"Unexpected Geocoding API status: {status}; response={payload}")


def _read_rows(path: str) -> Tuple[List[str], List[dict]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSVヘッダーが見つかりません")
        headers = list(reader.fieldnames)
        rows = list(reader)
    return headers, rows


def _ensure_columns(headers: List[str], extra_cols: Iterable[str]) -> List[str]:
    merged = list(headers)
    for col in extra_cols:
        if col not in merged:
            merged.append(col)
    return merged


def process_csv(
    input_csv: str,
    output_csv: str,
    geocoder: GoogleGeocoder,
    address_col: str = "住所",
    lat_col: str = "緯度",
    lng_col: str = "経度",
    formatted_address_col: str = "正規化住所",
) -> Tuple[int, int]:
    headers, rows = _read_rows(input_csv)
    if address_col not in headers:
        raise ValueError(f"住所列 '{address_col}' が入力CSVに存在しません: {headers}")

    out_headers = _ensure_columns(headers, [lat_col, lng_col, formatted_address_col])

    success = 0
    failed = 0
    for row in rows:
        address = (row.get(address_col) or "").strip()
        if not address:
            row[lat_col] = ""
            row[lng_col] = ""
            row[formatted_address_col] = ""
            failed += 1
            continue

        result = geocoder.geocode(address)

        if result is None:
            row[lat_col] = ""
            row[lng_col] = ""
            row[formatted_address_col] = ""
            failed += 1
        else:
            row[lat_col] = str(result.lat)
            row[lng_col] = str(result.lng)
            row[formatted_address_col] = result.formatted_address
            success += 1

    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_headers)
        writer.writeheader()
        writer.writerows(rows)

    return success, failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="住所付きCSVをGoogle Geocoding APIで緯度経度付きCSVに変換")
    parser.add_argument("input_csv", help="入力CSVパス")
    parser.add_argument("output_csv", help="出力CSVパス")
    parser.add_argument("--api-key", default=os.getenv("GOOGLE_MAPS_API_KEY"), help="Google Maps APIキー")
    parser.add_argument("--address-col", default="住所", help="住所カラム名")
    parser.add_argument("--lat-col", default="緯度", help="緯度カラム名")
    parser.add_argument("--lng-col", default="経度", help="経度カラム名")
    parser.add_argument("--formatted-address-col", default="正規化住所", help="正規化住所の出力カラム名")
    parser.add_argument("--sleep", type=float, default=0.1, help="API呼び出し間隔(秒)")
    parser.add_argument("--timeout", type=int, default=10, help="HTTPタイムアウト(秒)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.api_key:
        print("ERROR: APIキーがありません。--api-key または GOOGLE_MAPS_API_KEY を指定してください。", file=sys.stderr)
        return 2

    geocoder = GoogleGeocoder(api_key=args.api_key, sleep_seconds=args.sleep, timeout_seconds=args.timeout)
    try:
        success, failed = process_csv(
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            geocoder=geocoder,
            address_col=args.address_col,
            lat_col=args.lat_col,
            lng_col=args.lng_col,
            formatted_address_col=args.formatted_address_col,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total = success + failed
    print(f"完了: total={total}, success={success}, failed={failed}, output='{args.output_csv}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
