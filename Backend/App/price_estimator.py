from math import sqrt

from .database import get_connection


MIN_PRICE = 10000
MAX_PRICE = 2000000
MIN_SURFACE = 10
MAX_SURFACE = 500


def _normalize_text(value):
    return (value or "").strip().lower()


def _to_int(value):
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price_per_mp(ad):
    price = _to_float(ad.get("price_eur"))
    surface = _to_float(ad.get("surface_mp"))

    if not price or not surface or surface <= 0:
        return None

    return price / surface


def _percentile(values, percentile):
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower

    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _score_comparable(ad, target):
    score = 0
    reasons = []

    target_neighborhood = _normalize_text(target.get("neighborhood"))
    ad_neighborhood = _normalize_text(ad.get("neighborhood"))

    target_city = _normalize_text(target.get("city"))
    ad_city = _normalize_text(ad.get("city"))

    if target_neighborhood and ad_neighborhood == target_neighborhood:
        score += 55
        reasons.append("acelasi cartier")
    elif target_city and ad_city == target_city:
        score += 10
        reasons.append("acelasi oras")

    target_rooms = _to_int(target.get("rooms"))
    ad_rooms = _to_int(ad.get("rooms"))

    if target_rooms and ad_rooms:
        diff = abs(target_rooms - ad_rooms)
        if diff == 0:
            score += 22
            reasons.append("acelasi numar de camere")
        elif diff == 1:
            score += 8

    target_surface = _to_float(target.get("surface_mp"))
    ad_surface = _to_float(ad.get("surface_mp"))

    if target_surface and ad_surface:
        relative_diff = abs(target_surface - ad_surface) / target_surface
        surface_score = max(0, 30 * (1 - relative_diff / 0.45))
        score += surface_score

        if relative_diff <= 0.15:
            reasons.append("suprafata foarte apropiata")
        elif relative_diff <= 0.30:
            reasons.append("suprafata apropiata")

    target_floor = _to_int(target.get("floor"))
    ad_floor = _to_int(ad.get("floor"))

    if target_floor is not None and ad_floor is not None:
        floor_diff = abs(target_floor - ad_floor)
        if floor_diff == 0:
            score += 6
        elif floor_diff <= 2:
            score += 3

    target_year = _to_int(target.get("year_built"))
    ad_year = _to_int(ad.get("year_built"))

    if target_year and ad_year:
        year_diff = abs(target_year - ad_year)
        if year_diff <= 5:
            score += 10
            reasons.append("an constructie apropiat")
        elif year_diff <= 15:
            score += 5

    target_partitioning = _normalize_text(target.get("partitioning"))
    ad_partitioning = _normalize_text(ad.get("partitioning"))

    if target_partitioning and ad_partitioning == target_partitioning:
        score += 5

    return round(score, 2), reasons


def _fetch_candidate_ads(city=None):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            id,
            title,
            price_eur,
            surface_mp,
            rooms,
            neighborhood,
            city,
            floor,
            total_floors,
            year_built,
            partitioning,
            source,
            url,
            location_confidence
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND price_eur IS NOT NULL
          AND surface_mp IS NOT NULL
          AND surface_mp > 0
          AND price_eur BETWEEN ? AND ?
          AND surface_mp BETWEEN ? AND ?
    """
    params = [MIN_PRICE, MAX_PRICE, MIN_SURFACE, MAX_SURFACE]

    if city:
        query += " AND city = ?"
        params.append(city)

    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def _summarize_market(candidates, target):
    target_neighborhood = _normalize_text(target.get("neighborhood"))
    target_city = _normalize_text(target.get("city"))

    same_neighborhood = [
        ad
        for ad in candidates
        if _normalize_text(ad.get("neighborhood")) == target_neighborhood
    ]
    same_city = [
        ad
        for ad in candidates
        if _normalize_text(ad.get("city")) == target_city
    ]

    def summarize(rows):
        price_per_mp_values = [
            _price_per_mp(row)
            for row in rows
            if _price_per_mp(row) is not None
        ]

        if not price_per_mp_values:
            return {
                "count": 0,
                "avg_price_per_mp": None,
                "median_price_per_mp": None,
            }

        return {
            "count": len(price_per_mp_values),
            "avg_price_per_mp": round(sum(price_per_mp_values) / len(price_per_mp_values), 2),
            "median_price_per_mp": round(_percentile(price_per_mp_values, 0.5), 2),
        }

    return {
        "same_neighborhood": summarize(same_neighborhood),
        "same_city": summarize(same_city),
    }


def _build_comparables(candidates, target):
    comparables = []

    for ad in candidates:
        price_per_mp = _price_per_mp(ad)
        if price_per_mp is None:
            continue

        score, reasons = _score_comparable(ad, target)

        if score <= 0:
            continue

        comparables.append({
            **ad,
            "price_per_mp": round(price_per_mp, 2),
            "similarity_score": score,
            "match_reasons": reasons,
        })

    comparables.sort(
        key=lambda item: (item["similarity_score"], item["price_per_mp"]),
        reverse=True,
    )

    return comparables


def _fallback_comparables(candidates, target):
    target_surface = _to_float(target.get("surface_mp")) or 1

    rows = []
    for ad in candidates:
        price_per_mp = _price_per_mp(ad)
        if price_per_mp is None:
            continue

        ad_surface = _to_float(ad.get("surface_mp")) or target_surface
        surface_diff = abs(ad_surface - target_surface) / target_surface
        score = max(1, 25 * (1 - min(surface_diff, 1)))

        rows.append({
            **ad,
            "price_per_mp": round(price_per_mp, 2),
            "similarity_score": round(score, 2),
            "match_reasons": ["fallback pe suprafata"],
        })

    rows.sort(key=lambda item: item["similarity_score"], reverse=True)
    return rows


def _estimate_confidence(comparables, target):
    same_neighborhood_count = sum(
        1
        for ad in comparables
        if _normalize_text(ad.get("neighborhood")) == _normalize_text(target.get("neighborhood"))
    )

    if len(comparables) >= 25 and same_neighborhood_count >= 15:
        return "high"

    if len(comparables) >= 10 and same_neighborhood_count >= 5:
        return "medium"

    return "low"


def estimate_price(target):
    surface = _to_float(target.get("surface_mp"))
    rooms = _to_int(target.get("rooms"))

    if not surface or surface < MIN_SURFACE or surface > MAX_SURFACE:
        return {
            "error": "Suprafata trebuie sa fie intre 10 si 500 mp.",
        }

    if not rooms or rooms < 1 or rooms > 10:
        return {
            "error": "Numarul de camere trebuie sa fie intre 1 si 10.",
        }

    target = {
        **target,
        "surface_mp": surface,
        "rooms": rooms,
        "floor": _to_int(target.get("floor")),
        "total_floors": _to_int(target.get("total_floors")),
        "year_built": _to_int(target.get("year_built")),
        "neighborhood": (target.get("neighborhood") or "").strip(),
        "city": (target.get("city") or "Timisoara").strip(),
        "partitioning": (target.get("partitioning") or "").strip(),
    }

    candidates = _fetch_candidate_ads(city=target["city"])

    if not candidates:
        return {
            "error": "Nu exista suficiente anunturi valide pentru estimare.",
        }

    comparables = _build_comparables(candidates, target)

    if len(comparables) < 5:
        comparables = _fallback_comparables(candidates, target)

    selected = comparables[:40]

    if len(selected) < 3:
        return {
            "error": "Nu exista suficiente anunturi comparabile pentru estimare.",
        }

    weighted_sum = 0
    total_weight = 0
    weighted_values = []

    for ad in selected:
        weight = max(1, ad["similarity_score"])
        price_per_mp = ad["price_per_mp"]

        weighted_sum += price_per_mp * weight
        total_weight += weight
        weighted_values.extend([price_per_mp] * max(1, int(sqrt(weight))))

    estimated_price_per_mp = weighted_sum / total_weight

    p20 = _percentile(weighted_values, 0.20) or estimated_price_per_mp
    p80 = _percentile(weighted_values, 0.80) or estimated_price_per_mp

    estimated_price = round(estimated_price_per_mp * surface)
    low_estimate = round(p20 * surface * 0.96)
    high_estimate = round(p80 * surface * 1.04)

    if low_estimate > estimated_price:
        low_estimate = round(estimated_price * 0.92)

    if high_estimate < estimated_price:
        high_estimate = round(estimated_price * 1.08)

    confidence = _estimate_confidence(selected, target)
    market_summary = _summarize_market(candidates, target)

    return {
        "input": target,
        "estimate": {
            "estimated_price": estimated_price,
            "low_estimate": low_estimate,
            "high_estimate": high_estimate,
            "estimated_price_per_mp": round(estimated_price_per_mp, 2),
            "confidence": confidence,
            "sample_size": len(selected),
            "method": "weighted_comparable_ads",
        },
        "market_summary": market_summary,
        "comparables": selected[:10],
        "notes": [
            "Estimarea este statistica si foloseste anunturile active din baza de date.",
            "Pretul final poate varia in functie de finisaje, pozitie exacta, bloc si negociere.",
            "Modelul ML poate fi adaugat peste acest baseline dupa ce baza trece de un volum stabil de date.",
        ],
    }
