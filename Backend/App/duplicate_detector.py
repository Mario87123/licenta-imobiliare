import re
from collections import defaultdict

from .database import get_connection
from .location_resolver import normalize_text


DEFAULT_THRESHOLD = 92
BLOCK_INSERT_THRESHOLD = 97


def _number(value):
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value):
    number = _number(value)
    if number is None:
        return None
    return int(number)


def _norm(value):
    return normalize_text(value or "").strip()


def _title_tokens(title):
    normalized = _norm(title)
    tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
    stopwords = {
        "apartament",
        "vanzare",
        "camere",
        "camera",
        "decomandat",
        "semidecomandat",
        "timisoara",
        "timis",
        "zona",
    }
    return tokens - stopwords


def _title_similarity(title_a, title_b):
    tokens_a = _title_tokens(title_a)
    tokens_b = _title_tokens(title_b)

    if not tokens_a or not tokens_b:
        return 0

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)

    if union == 0:
        return 0

    return intersection / union


def _relative_diff(a, b):
    if a is None or b is None:
        return None

    baseline = max(abs(a), abs(b), 1)
    return abs(a - b) / baseline


def _is_reasonable_candidate(ad_a, ad_b):
    ad_a_id = ad_a.get("id")
    ad_b_id = ad_b.get("id")

    if ad_a_id is not None and ad_b_id is not None and ad_a_id == ad_b_id:
        return False

    if _norm(ad_a.get("source")) == _norm(ad_b.get("source")):
        return False

    if _norm(ad_a.get("city")) and _norm(ad_b.get("city")):
        if _norm(ad_a.get("city")) != _norm(ad_b.get("city")):
            return False

    if not _norm(ad_a.get("neighborhood")) or not _norm(ad_b.get("neighborhood")):
        return False

    if _norm(ad_a.get("neighborhood")) != _norm(ad_b.get("neighborhood")):
        return False

    rooms_a = _integer(ad_a.get("rooms"))
    rooms_b = _integer(ad_b.get("rooms"))
    if rooms_a is None or rooms_b is None or rooms_a != rooms_b:
        return False

    price_diff = _relative_diff(_number(ad_a.get("price_eur")), _number(ad_b.get("price_eur")))
    if price_diff is None or price_diff > 0.05:
        return False

    surface_a = _number(ad_a.get("surface_mp"))
    surface_b = _number(ad_b.get("surface_mp"))
    surface_diff = _relative_diff(surface_a, surface_b)

    if surface_diff is None or surface_diff > 0.08:
        return False

    if abs(surface_a - surface_b) > 5:
        return False

    title_similarity = _title_similarity(ad_a.get("title"), ad_b.get("title"))

    floor_a = _integer(ad_a.get("floor"))
    floor_b = _integer(ad_b.get("floor"))
    same_known_floor = (
        floor_a is not None
        and floor_b is not None
        and floor_a == floor_b
    )

    very_close_numbers = price_diff <= 0.015 and abs(surface_a - surface_b) <= 2
    title_support = title_similarity >= 0.16
    floor_title_support = same_known_floor and title_similarity >= 0.06

    if not (very_close_numbers or title_support or floor_title_support):
        return False

    return True


def score_duplicate_pair(ad_a, ad_b):
    if not _is_reasonable_candidate(ad_a, ad_b):
        return 0

    score = 0

    score += 35  # same neighborhood, required by candidate filter
    score += 15  # same rooms, required by candidate filter

    price_diff = _relative_diff(_number(ad_a.get("price_eur")), _number(ad_b.get("price_eur")))
    if price_diff <= 0.01:
        score += 25
    elif price_diff <= 0.03:
        score += 20
    elif price_diff <= 0.05:
        score += 15
    else:
        score += 8

    surface_a = _number(ad_a.get("surface_mp"))
    surface_b = _number(ad_b.get("surface_mp"))
    surface_abs_diff = abs(surface_a - surface_b)

    if surface_abs_diff <= 1:
        score += 20
    elif surface_abs_diff <= 3:
        score += 16
    elif surface_abs_diff <= 5:
        score += 12
    else:
        score += 7

    floor_a = _integer(ad_a.get("floor"))
    floor_b = _integer(ad_b.get("floor"))
    if floor_a is not None and floor_b is not None:
        if floor_a == floor_b:
            score += 7
        elif abs(floor_a - floor_b) <= 1:
            score += 3

    total_floors_a = _integer(ad_a.get("total_floors"))
    total_floors_b = _integer(ad_b.get("total_floors"))
    if total_floors_a is not None and total_floors_b is not None:
        if total_floors_a == total_floors_b:
            score += 3

    year_a = _integer(ad_a.get("year_built"))
    year_b = _integer(ad_b.get("year_built"))
    if year_a is not None and year_b is not None:
        if year_a == year_b:
            score += 6
        elif abs(year_a - year_b) <= 3:
            score += 3

    if _norm(ad_a.get("partitioning")) and _norm(ad_a.get("partitioning")) == _norm(ad_b.get("partitioning")):
        score += 3

    title_similarity = _title_similarity(ad_a.get("title"), ad_b.get("title"))
    score += min(10, round(title_similarity * 10))

    return min(100, round(score, 2))


def _fetch_ads_for_detection():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
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
            location_confidence,
            created_at
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND price_eur IS NOT NULL
          AND surface_mp IS NOT NULL
          AND rooms IS NOT NULL
          AND neighborhood IS NOT NULL
          AND source IS NOT NULL
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def _choose_canonical(group_ads):
    confidence_rank = {
        "high": 3,
        "medium": 2,
        "low": 1,
    }

    def completeness(ad):
        fields = [
            "title",
            "price_eur",
            "surface_mp",
            "rooms",
            "neighborhood",
            "floor",
            "total_floors",
            "year_built",
            "partitioning",
        ]
        return sum(1 for field in fields if ad.get(field) not in (None, ""))

    return sorted(
        group_ads,
        key=lambda ad: (
            confidence_rank.get(_norm(ad.get("location_confidence")), 0),
            completeness(ad),
            -ad["id"],
        ),
        reverse=True,
    )[0]


def _build_groups(edges, ads_by_id):
    groups = []
    assigned_group_by_ad_id = {}

    sorted_edges = sorted(edges, key=lambda edge: edge[2], reverse=True)

    for ad_a_id, ad_b_id, score in sorted_edges:
        group_a = assigned_group_by_ad_id.get(ad_a_id)
        group_b = assigned_group_by_ad_id.get(ad_b_id)

        if group_a is not None and group_b is not None:
            continue

        if group_a is None and group_b is None:
            groups.append({
                "ads": [ads_by_id[ad_a_id], ads_by_id[ad_b_id]],
                "pair_scores": {frozenset({ad_a_id, ad_b_id}): score},
            })
            group_index = len(groups) - 1
            assigned_group_by_ad_id[ad_a_id] = group_index
            assigned_group_by_ad_id[ad_b_id] = group_index
            continue

        group_index = group_a if group_a is not None else group_b
        new_ad_id = ad_b_id if group_a is not None else ad_a_id
        new_ad = ads_by_id[new_ad_id]

        existing_sources = {
            _norm(ad.get("source"))
            for ad in groups[group_index]["ads"]
        }

        if _norm(new_ad.get("source")) in existing_sources:
            continue

        canonical = _choose_canonical(groups[group_index]["ads"])
        canonical_pair_score = score_duplicate_pair(canonical, new_ad)

        if canonical_pair_score < DEFAULT_THRESHOLD:
            continue

        groups[group_index]["ads"].append(new_ad)
        groups[group_index]["pair_scores"][frozenset({canonical["id"], new_ad_id})] = canonical_pair_score
        assigned_group_by_ad_id[new_ad_id] = group_index

    final_groups = []
    for group in groups:
        if len(group["ads"]) < 2:
            continue

        group["canonical"] = _choose_canonical(group["ads"])
        final_groups.append(group)

    return final_groups


def detect_duplicate_groups(threshold: int = DEFAULT_THRESHOLD):
    ads = _fetch_ads_for_detection()
    ads_by_id = {ad["id"]: ad for ad in ads}

    buckets = defaultdict(list)
    for ad in ads:
        key = (
            _norm(ad.get("city")),
            _norm(ad.get("neighborhood")),
            _integer(ad.get("rooms")),
        )
        buckets[key].append(ad)

    edges = []
    comparisons = 0

    for bucket_ads in buckets.values():
        for index, ad_a in enumerate(bucket_ads):
            for ad_b in bucket_ads[index + 1:]:
                comparisons += 1
                score = score_duplicate_pair(ad_a, ad_b)
                if score >= threshold:
                    edges.append((ad_a["id"], ad_b["id"], score))

    groups = _build_groups(edges, ads_by_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE ads
        SET duplicate_group_id = NULL,
            canonical_ad_id = NULL,
            duplicate_score = NULL
    """)

    updated_ads = 0
    for group in groups:
        canonical = group["canonical"]
        canonical_id = canonical["id"]
        group_id = canonical_id

        for ad in group["ads"]:
            if ad["id"] == canonical_id:
                score = 100
            else:
                score = max(
                    (
                        group["pair_scores"].get(frozenset({ad["id"], other["id"]}), 0)
                        for other in group["ads"]
                        if other["id"] != ad["id"]
                    ),
                    default=0,
                )

            cursor.execute("""
                UPDATE ads
                SET duplicate_group_id = ?,
                    canonical_ad_id = ?,
                    duplicate_score = ?
                WHERE id = ?
            """, (group_id, canonical_id, score, ad["id"]))
            updated_ads += 1

    conn.commit()
    conn.close()

    return {
        "threshold": threshold,
        "ads_scanned": len(ads),
        "comparisons": comparisons,
        "duplicate_groups": len(groups),
        "ads_marked": updated_ads,
    }


def find_existing_duplicate_for_ad(ad, threshold: int = BLOCK_INSERT_THRESHOLD):
    if not ad:
        return None

    source = _norm(ad.get("source"))
    neighborhood = ad.get("neighborhood")
    city = ad.get("city")
    rooms = ad.get("rooms")
    price = _number(ad.get("price_eur"))
    surface = _number(ad.get("surface_mp"))

    if not source or not neighborhood or not rooms or not price or not surface:
        return None

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
            location_confidence,
            created_at
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND source IS NOT NULL
          AND source != ?
          AND neighborhood = ?
          AND rooms = ?
          AND price_eur IS NOT NULL
          AND surface_mp IS NOT NULL
          AND price_eur BETWEEN ? AND ?
          AND surface_mp BETWEEN ? AND ?
    """

    params = [
        source,
        neighborhood,
        rooms,
        round(price * 0.95),
        round(price * 1.05),
        surface - 5,
        surface + 5,
    ]

    if city:
        query += " AND (city = ? OR city IS NULL)"
        params.append(city)

    cursor.execute(query, params)
    candidates = [dict(row) for row in cursor.fetchall()]
    conn.close()

    best_match = None
    best_score = 0

    for candidate in candidates:
        score = score_duplicate_pair(ad, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_match and best_score >= threshold:
        return {
            "matched_ad": best_match,
            "score": best_score,
            "threshold": threshold,
        }

    return None


def save_rejected_duplicate_ad(ad, duplicate_match, source_label: str = None):
    if not ad or not duplicate_match:
        return

    matched_ad = duplicate_match["matched_ad"]
    score = duplicate_match["score"]
    source = ad.get("source") or source_label
    url = ad.get("url")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO rejected_duplicate_ads (
            source,
            url,
            matched_ad_id,
            duplicate_score,
            title,
            price_eur,
            surface_mp,
            rooms,
            neighborhood,
            city,
            reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url, source) DO UPDATE SET
            matched_ad_id = excluded.matched_ad_id,
            duplicate_score = excluded.duplicate_score,
            title = excluded.title,
            price_eur = excluded.price_eur,
            surface_mp = excluded.surface_mp,
            rooms = excluded.rooms,
            neighborhood = excluded.neighborhood,
            city = excluded.city,
            reason = excluded.reason
    """, (
        source,
        url,
        matched_ad["id"],
        score,
        ad.get("title"),
        ad.get("price_eur"),
        ad.get("surface_mp"),
        ad.get("rooms"),
        ad.get("neighborhood"),
        ad.get("city"),
        "cross_source_duplicate",
    ))

    conn.commit()
    conn.close()


def get_rejected_duplicate_ads(limit: int = 100):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            rejected_duplicate_ads.*,
            ads.title AS matched_title,
            ads.source AS matched_source,
            ads.url AS matched_url
        FROM rejected_duplicate_ads
        LEFT JOIN ads ON ads.id = rejected_duplicate_ads.matched_ad_id
        ORDER BY rejected_duplicate_ads.created_at DESC, rejected_duplicate_ads.id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_duplicate_groups():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM ads
        WHERE duplicate_group_id IS NOT NULL
        ORDER BY duplicate_group_id ASC, canonical_ad_id = id DESC, duplicate_score DESC
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    groups = defaultdict(list)
    for row in rows:
        groups[row["duplicate_group_id"]].append(row)

    return [
        {
            "group_id": group_id,
            "canonical_ad_id": items[0]["canonical_ad_id"],
            "count": len(items),
            "items": items,
        }
        for group_id, items in groups.items()
    ]
