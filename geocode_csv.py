#!/usr/bin/env python3
"""CSVの住所列をGoogle APIで緯度経度に変換するスクリプト。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    formatted_address: str
    location_type: str = ""


@dataclass
class GeocodeFailure:
    status: str
    message: str


@dataclass
class GeocodeResponse:
    result: Optional[GeocodeResult]
    failure: Optional[GeocodeFailure] = None


@dataclass
class PlaceCandidate:
    place_id: str
    name: str
    formatted_address: str
    lat: float
    lng: float


@dataclass
class PlaceMatch:
    candidate: PlaceCandidate
    score: float
    confidence: str
    reasons: List[str]


class GoogleGeocoder:
    def __init__(self, api_key: str, sleep_seconds: float = 0.1, timeout_seconds: int = 10) -> None:
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: Dict[str, GeocodeResponse] = {}

    def geocode(self, address: str) -> GeocodeResponse:
        address = address.strip()
        if not address:
            return GeocodeResponse(result=None, failure=GeocodeFailure(status="EMPTY_ADDRESS", message="住所が空です"))

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
                location_type=top.get("geometry", {}).get("location_type", ""),
            )
            response = GeocodeResponse(result=result)
            self._cache[address] = response
            time.sleep(self.sleep_seconds)
            return response

        if status in {"ZERO_RESULTS", "OVER_DAILY_LIMIT", "OVER_QUERY_LIMIT", "REQUEST_DENIED", "INVALID_REQUEST"}:
            error_message = payload.get("error_message") or ""
            failure_message = error_message if error_message else "Geocoding APIが結果を返しませんでした"
            response = GeocodeResponse(
                result=None,
                failure=GeocodeFailure(status=status, message=failure_message),
            )
            self._cache[address] = response
            time.sleep(self.sleep_seconds)
            return response

        raise RuntimeError(f"Unexpected Geocoding API status: {status}; response={payload}")


class GooglePlacesMatcher:
    def __init__(self, api_key: str, sleep_seconds: float = 0.1, timeout_seconds: int = 10) -> None:
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: Dict[str, List[PlaceCandidate]] = {}

    def find_candidates(self, query: str, locationbias: Optional[str] = None) -> List[PlaceCandidate]:
        query = query.strip()
        if not query:
            return []

        cache_key = f"{query}::{locationbias or ''}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        params = {
            "input": query,
            "inputtype": "textquery",
            "fields": "place_id,name,formatted_address,geometry",
            "language": "ja",
            "region": "jp",
            "key": self.api_key,
        }
        if locationbias:
            params["locationbias"] = locationbias

        url = f"{FIND_PLACE_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url=url, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Places APIリクエスト失敗: query='{query}', error={exc}") from exc

        status = payload.get("status")
        if status not in {"OK", "ZERO_RESULTS"}:
            error_message = payload.get("error_message") or ""
            raise RuntimeError(f"Places API失敗: status={status}, message={error_message}")

        candidates: List[PlaceCandidate] = []
        for c in payload.get("candidates", []):
            loc = c.get("geometry", {}).get("location") or {}
            if "lat" not in loc or "lng" not in loc:
                continue
            candidates.append(
                PlaceCandidate(
                    place_id=c.get("place_id", ""),
                    name=c.get("name", ""),
                    formatted_address=c.get("formatted_address", ""),
                    lat=float(loc["lat"]),
                    lng=float(loc["lng"]),
                )
            )

        self._cache[cache_key] = candidates
        time.sleep(self.sleep_seconds)
        return candidates


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


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").lower())


def _extract_postal_code(text: str) -> str:
    m = re.search(r"(\d{3})-?(\d{4})", text or "")
    return "" if not m else f"{m.group(1)}{m.group(2)}"


def _name_similarity(a: str, b: str) -> float:
    sa = set(_normalize_text(a))
    sb = set(_normalize_text(b))
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _contains_any(haystack: str, needles: Iterable[str]) -> int:
    normalized = _normalize_text(haystack)
    score = 0
    for n in needles:
        nn = _normalize_text(n)
        if nn and nn in normalized:
            score += 1
    return score


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _build_locationbias(geocode_result: Optional[GeocodeResult], radius_m: int) -> Optional[str]:
    if geocode_result is None:
        return None
    return f"circle:{int(radius_m)}@{geocode_result.lat},{geocode_result.lng}"


def _score_candidate(
    candidate: PlaceCandidate,
    shop_name: str,
    raw_address: str,
    geocode_result: Optional[GeocodeResult],
) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0

    name_sim = _name_similarity(shop_name, candidate.name)
    score += name_sim * 45.0
    reasons.append(f"name_sim={name_sim:.2f}")

    raw_zip = _extract_postal_code(raw_address)
    cand_zip = _extract_postal_code(candidate.formatted_address)
    if raw_zip and cand_zip:
        if raw_zip == cand_zip:
            score += 25.0
            reasons.append("zip_match")
        else:
            score -= 10.0
            reasons.append("zip_mismatch")

    address_tokens = [t for t in re.split(r"[\s,、　]+", raw_address or "") if len(t) >= 2]
    token_hits = _contains_any(candidate.formatted_address, address_tokens[:6])
    score += min(token_hits * 3.0, 18.0)
    reasons.append(f"addr_token_hits={token_hits}")

    if geocode_result is not None:
        dist = _haversine_m(geocode_result.lat, geocode_result.lng, candidate.lat, candidate.lng)
        if dist <= 100:
            score += 12.0
        elif dist <= 300:
            score += 8.0
        elif dist <= 1000:
            score += 4.0
        elif dist > 5000:
            score -= 8.0
        reasons.append(f"dist_m={dist:.0f}")

    if "restaurant" in _normalize_text(candidate.formatted_address):
        score += 1.0

    return score, reasons


def _classify_confidence(best_score: float, second_score: float) -> str:
    gap = best_score - second_score
    if best_score >= 65 and gap >= 10:
        return "high"
    if best_score >= 45 and gap >= 5:
        return "medium"
    return "low"


def _select_place_match(
    candidates: List[PlaceCandidate],
    shop_name: str,
    raw_address: str,
    geocode_result: Optional[GeocodeResult],
) -> Optional[PlaceMatch]:
    if not candidates:
        return None

    scored: List[Tuple[PlaceCandidate, float, List[str]]] = []
    for c in candidates:
        s, reasons = _score_candidate(c, shop_name, raw_address, geocode_result)
        scored.append((c, s, reasons))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_c, best_s, best_reasons = scored[0]
    second_s = scored[1][1] if len(scored) > 1 else -999.0
    confidence = _classify_confidence(best_s, second_s)
    return PlaceMatch(candidate=best_c, score=best_s, confidence=confidence, reasons=best_reasons)


def process_csv(
    input_csv: str,
    output_csv: str,
    geocoder: GoogleGeocoder,
    places_matcher: Optional[GooglePlacesMatcher],
    address_col: str = "住所",
    name_col: str = "店の名前",
    lat_col: str = "緯度",
    lng_col: str = "経度",
    formatted_address_col: str = "正規化住所",
    failure_reason_col: str = "ジオコーディング失敗理由",
    match_method_col: str = "採用方式",
    confidence_col: str = "信頼度",
    place_id_col: str = "place_id",
    matched_name_col: str = "候補店名(採用)",
    matched_address_col: str = "候補住所(採用)",
    matched_lat_col: str = "候補緯度(採用)",
    matched_lng_col: str = "候補経度(採用)",
    match_score_col: str = "候補スコア",
    fallback_reason_col: str = "フォールバック理由",
    distance_col: str = "places_geocode_distance_m",
    places_bias_radius_m: int = 3000,
) -> Tuple[int, int]:
    headers, rows = _read_rows(input_csv)
    if address_col not in headers:
        raise ValueError(f"住所列 '{address_col}' が入力CSVに存在しません: {headers}")

    out_headers = _ensure_columns(
        headers,
        [
            lat_col,
            lng_col,
            formatted_address_col,
            failure_reason_col,
            match_method_col,
            confidence_col,
            place_id_col,
            matched_name_col,
            matched_address_col,
            matched_lat_col,
            matched_lng_col,
            match_score_col,
            fallback_reason_col,
            distance_col,
        ],
    )

    success = 0
    failed = 0
    for i, row in enumerate(rows, start=2):
        address = (row.get(address_col) or "").strip()
        shop_name = (row.get(name_col) or "").strip()

        row[place_id_col] = ""
        row[matched_name_col] = ""
        row[matched_address_col] = ""
        row[match_score_col] = ""
        row[matched_lat_col] = ""
        row[matched_lng_col] = ""
        row[fallback_reason_col] = ""
        row[distance_col] = ""

        if not address:
            row[lat_col] = ""
            row[lng_col] = ""
            row[formatted_address_col] = ""
            row[failure_reason_col] = "EMPTY_ADDRESS: 住所が空です"
            row[match_method_col] = "none"
            row[confidence_col] = "low"
            failed += 1
            continue

        # まず住所ジオコーディングを行い、フォールバック先および Places のバイアス原点に使う。
        geo = geocoder.geocode(address)
        geocode_result = geo.result

        # Places マッチング
        place_match: Optional[PlaceMatch] = None
        if places_matcher is not None and shop_name:
            query = f"{shop_name} {address}"
            locationbias = _build_locationbias(geocode_result, places_bias_radius_m)
            candidates = places_matcher.find_candidates(query=query, locationbias=locationbias)
            place_match = _select_place_match(candidates, shop_name=shop_name, raw_address=address, geocode_result=geocode_result)

        # Places が高/中信頼なら採用。低信頼または候補なしなら Geocoding を採用。
        if place_match is not None and place_match.confidence in {"high", "medium"}:
            row[lat_col] = str(place_match.candidate.lat)
            row[lng_col] = str(place_match.candidate.lng)
            row[formatted_address_col] = place_match.candidate.formatted_address
            row[failure_reason_col] = ""
            row[match_method_col] = "places"
            row[confidence_col] = place_match.confidence
            row[place_id_col] = place_match.candidate.place_id
            row[matched_name_col] = place_match.candidate.name
            row[matched_address_col] = place_match.candidate.formatted_address
            row[match_score_col] = f"{place_match.score:.2f}"
            row[matched_lat_col] = str(place_match.candidate.lat)
            row[matched_lng_col] = str(place_match.candidate.lng)
            if geocode_result is not None:
                dist = _haversine_m(geocode_result.lat, geocode_result.lng, place_match.candidate.lat, place_match.candidate.lng)
                row[distance_col] = f"{dist:.1f}"
            success += 1
            continue

        # Geocoding fallback
        if geocode_result is None:
            row[lat_col] = ""
            row[lng_col] = ""
            row[formatted_address_col] = ""
            status = geo.failure.status if geo.failure else "UNKNOWN"
            message = geo.failure.message if geo.failure else "原因不明"
            row[failure_reason_col] = f"{status}: {message}"
            row[match_method_col] = "none"
            row[confidence_col] = "low"
            row[fallback_reason_col] = "GEOCODE_FAILED"
            print(f"WARN row={i} address='{address}' -> {row[failure_reason_col]}", file=sys.stderr)
            failed += 1
            continue

        row[lat_col] = str(geocode_result.lat)
        row[lng_col] = str(geocode_result.lng)
        row[formatted_address_col] = geocode_result.formatted_address
        row[failure_reason_col] = ""
        row[match_method_col] = "geocode_fallback"
        row[confidence_col] = "medium" if geocode_result.location_type == "ROOFTOP" else "low"
        if place_match is None:
            row[fallback_reason_col] = "NO_PLACE_CANDIDATE"
        else:
            row[fallback_reason_col] = f"LOW_PLACE_CONFIDENCE:{place_match.confidence}"
            row[place_id_col] = place_match.candidate.place_id
            row[matched_name_col] = place_match.candidate.name
            row[matched_address_col] = place_match.candidate.formatted_address
            row[match_score_col] = f"{place_match.score:.2f}"
            row[matched_lat_col] = str(place_match.candidate.lat)
            row[matched_lng_col] = str(place_match.candidate.lng)
            dist = _haversine_m(geocode_result.lat, geocode_result.lng, place_match.candidate.lat, place_match.candidate.lng)
            row[distance_col] = f"{dist:.1f}"
        success += 1

    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_headers)
        writer.writeheader()
        writer.writerows(rows)

    return success, failed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="住所付きCSVをGoogle APIで緯度経度付きCSVに変換")
    parser.add_argument("input_csv", help="入力CSVパス")
    parser.add_argument("output_csv", help="出力CSVパス")
    parser.add_argument("--api-key", default=os.getenv("GOOGLE_MAPS_API_KEY"), help="Google Maps APIキー")
    parser.add_argument("--address-col", default="住所", help="住所カラム名")
    parser.add_argument("--name-col", default="店の名前", help="店名カラム名")
    parser.add_argument("--lat-col", default="緯度", help="緯度カラム名")
    parser.add_argument("--lng-col", default="経度", help="経度カラム名")
    parser.add_argument("--formatted-address-col", default="正規化住所", help="正規化住所の出力カラム名")
    parser.add_argument(
        "--failure-reason-col",
        default="ジオコーディング失敗理由",
        help="失敗理由の出力カラム名",
    )
    parser.add_argument("--disable-places", action="store_true", help="Places API検索を行わず住所Geocodingのみ利用")
    parser.add_argument("--places-bias-radius", type=int, default=3000, help="Places検索バイアス半径(メートル)")
    parser.add_argument("--sleep", type=float, default=0.1, help="API呼び出し間隔(秒)")
    parser.add_argument("--timeout", type=int, default=10, help="HTTPタイムアウト(秒)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.api_key:
        print("ERROR: APIキーがありません。--api-key または GOOGLE_MAPS_API_KEY を指定してください。", file=sys.stderr)
        return 2

    geocoder = GoogleGeocoder(api_key=args.api_key, sleep_seconds=args.sleep, timeout_seconds=args.timeout)
    places_matcher = None if args.disable_places else GooglePlacesMatcher(
        api_key=args.api_key,
        sleep_seconds=args.sleep,
        timeout_seconds=args.timeout,
    )
    try:
        success, failed = process_csv(
            input_csv=args.input_csv,
            output_csv=args.output_csv,
            geocoder=geocoder,
            places_matcher=places_matcher,
            address_col=args.address_col,
            name_col=args.name_col,
            lat_col=args.lat_col,
            lng_col=args.lng_col,
            formatted_address_col=args.formatted_address_col,
            failure_reason_col=args.failure_reason_col,
            places_bias_radius_m=args.places_bias_radius,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    total = success + failed
    print(f"完了: total={total}, success={success}, failed={failed}, output='{args.output_csv}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
