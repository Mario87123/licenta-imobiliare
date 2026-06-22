from .database import get_connection
from .ml_price_model import get_ml_model_status
from .neighborhood_catalog import NEIGHBORHOODS


LOW_PRICE_PER_MP = 700
HIGH_PRICE_PER_MP = 4500


def _fetch_one(cursor, query, params=()):
    cursor.execute(query, params)
    row = cursor.fetchone()
    return dict(row) if row else {}


def _fetch_all(cursor, query, params=()):
    cursor.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def _count(cursor, query, params=()):
    row = _fetch_one(cursor, query, params)
    return int(row.get("count") or 0)


def _percentage(part, total):
    if not total:
        return 0

    return round((part / total) * 100, 2)


def _build_issue(code, severity, title, detail, count=None):
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "detail": detail,
        "count": count,
    }


def _build_readiness_score(issues):
    penalty_by_severity = {
        "critical": 18,
        "warning": 8,
        "info": 3,
    }

    score = 100
    for issue in issues:
        score -= penalty_by_severity.get(issue["severity"], 0)

    score = max(0, score)

    if score >= 85:
        status = "good"
    elif score >= 65:
        status = "warning"
    else:
        status = "critical"

    return {
        "score": score,
        "status": status,
    }


def get_data_quality_audit():
    conn = get_connection()
    cursor = conn.cursor()

    total_ads = _count(
        cursor,
        "SELECT COUNT(*) AS count FROM ads WHERE COALESCE(is_active, 1) = 1",
    )

    inactive_ads = _count(
        cursor,
        "SELECT COUNT(*) AS count FROM ads WHERE COALESCE(is_active, 1) = 0",
    )

    estimator_ready = _count(
        cursor,
        """
        SELECT COUNT(*) AS count
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND price_eur IS NOT NULL
          AND price_eur > 0
          AND surface_mp IS NOT NULL
          AND surface_mp > 0
          AND rooms IS NOT NULL
          AND neighborhood IS NOT NULL
        """,
    )

    missing = _fetch_one(
        cursor,
        """
        SELECT
            SUM(CASE WHEN neighborhood IS NULL OR TRIM(neighborhood) = '' THEN 1 ELSE 0 END) AS neighborhood,
            SUM(CASE WHEN city IS NULL OR TRIM(city) = '' THEN 1 ELSE 0 END) AS city,
            SUM(CASE WHEN price_eur IS NULL OR price_eur <= 0 THEN 1 ELSE 0 END) AS price,
            SUM(CASE WHEN surface_mp IS NULL OR surface_mp <= 0 THEN 1 ELSE 0 END) AS surface,
            SUM(CASE WHEN rooms IS NULL OR rooms <= 0 THEN 1 ELSE 0 END) AS rooms,
            SUM(CASE WHEN year_built IS NULL THEN 1 ELSE 0 END) AS year_built,
            SUM(CASE WHEN floor IS NULL THEN 1 ELSE 0 END) AS floor,
            SUM(CASE WHEN location_confidence = 'low' THEN 1 ELSE 0 END) AS low_confidence
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
        """,
    )

    price_per_mp_outliers_count = _count(
        cursor,
        """
        SELECT COUNT(*) AS count
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND price_eur IS NOT NULL
          AND surface_mp IS NOT NULL
          AND surface_mp > 0
          AND (
            price_eur * 1.0 / surface_mp < ?
            OR price_eur * 1.0 / surface_mp > ?
          )
        """,
        (LOW_PRICE_PER_MP, HIGH_PRICE_PER_MP),
    )

    price_per_mp_outliers = _fetch_all(
        cursor,
        """
        SELECT
            id,
            source,
            title,
            neighborhood,
            city,
            price_eur,
            surface_mp,
            ROUND(price_eur * 1.0 / surface_mp, 2) AS price_per_mp,
            url
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND price_eur IS NOT NULL
          AND surface_mp IS NOT NULL
          AND surface_mp > 0
          AND (
            price_eur * 1.0 / surface_mp < ?
            OR price_eur * 1.0 / surface_mp > ?
          )
        ORDER BY price_per_mp DESC
        LIMIT 20
        """,
        (LOW_PRICE_PER_MP, HIGH_PRICE_PER_MP),
    )

    by_source = _fetch_all(
        cursor,
        """
        SELECT
            source,
            COUNT(*) AS count_ads,
            ROUND(AVG(price_eur), 2) AS avg_price,
            ROUND(AVG(surface_mp), 2) AS avg_surface,
            ROUND(AVG(CASE WHEN surface_mp > 0 THEN price_eur * 1.0 / surface_mp ELSE NULL END), 2) AS avg_price_per_mp
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
        GROUP BY source
        ORDER BY count_ads DESC
        """,
    )

    by_city = _fetch_all(
        cursor,
        """
        SELECT city, COUNT(*) AS count_ads
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
        GROUP BY city
        ORDER BY count_ads DESC
        """,
    )

    by_confidence = _fetch_all(
        cursor,
        """
        SELECT location_confidence, COUNT(*) AS count_ads
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
        GROUP BY location_confidence
        ORDER BY count_ads DESC
        """,
    )

    low_sample_neighborhoods = _fetch_all(
        cursor,
        """
        SELECT
            neighborhood,
            city,
            COUNT(*) AS count_ads,
            ROUND(AVG(CASE WHEN surface_mp > 0 THEN price_eur * 1.0 / surface_mp ELSE NULL END), 2) AS avg_price_per_mp
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND neighborhood IS NOT NULL
        GROUP BY neighborhood, city
        HAVING COUNT(*) < 3
        ORDER BY count_ads ASC, neighborhood ASC
        LIMIT 20
        """,
    )

    catalog_names = {name.lower() for name in NEIGHBORHOODS.keys()}
    distinct_neighborhoods = _fetch_all(
        cursor,
        """
        SELECT DISTINCT neighborhood
        FROM ads
        WHERE COALESCE(is_active, 1) = 1
          AND neighborhood IS NOT NULL
        ORDER BY neighborhood
        """,
    )
    unknown_neighborhoods = [
        item["neighborhood"]
        for item in distinct_neighborhoods
        if item["neighborhood"].lower() not in catalog_names
    ]

    duplicate_summary = _fetch_one(
        cursor,
        """
        SELECT
            COUNT(DISTINCT duplicate_group_id) AS duplicate_groups,
            COUNT(*) AS duplicate_ads
        FROM ads
        WHERE duplicate_group_id IS NOT NULL
        """,
    )

    rejected_duplicates_count = _count(
        cursor,
        "SELECT COUNT(*) AS count FROM rejected_duplicate_ads",
    )

    ignored_by_reason = _fetch_all(
        cursor,
        """
        SELECT source, reason, COUNT(*) AS count
        FROM ignored_listing_urls
        GROUP BY source, reason
        ORDER BY count DESC
        LIMIT 20
        """,
    )

    crawl_jobs_summary = _fetch_all(
        cursor,
        """
        SELECT status, COUNT(*) AS count
        FROM crawl_jobs
        GROUP BY status
        ORDER BY count DESC
        """,
    )

    active_jobs = _count(
        cursor,
        """
        SELECT COUNT(*) AS count
        FROM crawl_jobs
        WHERE status IN ('pending', 'running', 'cancelling')
        """,
    )

    latest_jobs = _fetch_all(
        cursor,
        """
        SELECT
            id,
            source,
            mode,
            status,
            ads_discovered,
            ads_processed,
            ads_inserted,
            ads_updated,
            error_count,
            blocked_count,
            started_at,
            finished_at
        FROM crawl_jobs
        ORDER BY id DESC
        LIMIT 5
        """,
    )

    conn.close()

    ml_status = get_ml_model_status()

    missing = {key: int(value or 0) for key, value in missing.items()}
    issues = []

    if total_ads == 0:
        issues.append(_build_issue(
            "empty_database",
            "critical",
            "Baza de date este goala",
            "Ruleaza un backfill inainte de hosting sau demo.",
            total_ads,
        ))

    if estimator_ready < 80:
        issues.append(_build_issue(
            "low_estimator_samples",
            "warning",
            "Putine anunturi valide pentru estimator",
            "Estimatorul ML/statistic devine mai stabil dupa ce ai cel putin 80-100 de anunturi complete.",
            estimator_ready,
        ))

    if missing["neighborhood"] > 0:
        issues.append(_build_issue(
            "missing_neighborhood",
            "critical",
            "Exista anunturi fara cartier",
            "Acestea nu pot fi folosite corect in harta si in estimatorul pe zone.",
            missing["neighborhood"],
        ))

    if _percentage(missing["surface"], total_ads) > 10:
        issues.append(_build_issue(
            "missing_surface",
            "warning",
            "Multe anunturi fara suprafata",
            "Suprafata este esentiala pentru pret/mp si estimare.",
            missing["surface"],
        ))

    if _percentage(missing["rooms"], total_ads) > 10:
        issues.append(_build_issue(
            "missing_rooms",
            "warning",
            "Multe anunturi fara numar de camere",
            "Numarul de camere este o caracteristica importanta pentru comparabile.",
            missing["rooms"],
        ))

    if missing["low_confidence"] > 0:
        issues.append(_build_issue(
            "low_confidence_locations",
            "info",
            "Exista locatii cu incredere scazuta",
            "Merita verificate dupa crawl-uri mari, mai ales pentru Storia.",
            missing["low_confidence"],
        ))

    if price_per_mp_outliers_count > 0:
        issues.append(_build_issue(
            "price_per_mp_outliers",
            "warning",
            "Exista preturi/mp extreme",
            f"Pragul folosit este sub {LOW_PRICE_PER_MP} EUR/mp sau peste {HIGH_PRICE_PER_MP} EUR/mp.",
            price_per_mp_outliers_count,
        ))

    if unknown_neighborhoods:
        issues.append(_build_issue(
            "unknown_neighborhoods",
            "warning",
            "Exista cartiere care nu sunt in catalog",
            "Aceste nume pot sa nu se potriveasca bine cu harta GeoJSON.",
            len(unknown_neighborhoods),
        ))

    if active_jobs > 0:
        issues.append(_build_issue(
            "active_jobs",
            "info",
            "Exista joburi crawler active",
            "Asteapta finalizarea lor inainte de auditul final.",
            active_jobs,
        ))

    if not ml_status.get("is_trained"):
        issues.append(_build_issue(
            "ml_not_trained",
            "warning",
            "Modelul ML nu este antrenat",
            "Antreneaza modelul dupa crawl-ul final.",
        ))

    readiness = _build_readiness_score(issues)

    return {
        "readiness": readiness,
        "summary": {
            "active_ads": total_ads,
            "inactive_ads": inactive_ads,
            "estimator_ready_ads": estimator_ready,
            "estimator_ready_percent": _percentage(estimator_ready, total_ads),
            "price_per_mp_low_threshold": LOW_PRICE_PER_MP,
            "price_per_mp_high_threshold": HIGH_PRICE_PER_MP,
        },
        "quality": {
            "missing": {
                key: {
                    "count": value,
                    "percent": _percentage(value, total_ads),
                }
                for key, value in missing.items()
            },
            "price_per_mp_outliers_count": price_per_mp_outliers_count,
            "unknown_neighborhoods": unknown_neighborhoods,
            "low_sample_neighborhoods": low_sample_neighborhoods,
        },
        "distribution": {
            "by_source": by_source,
            "by_city": by_city,
            "by_confidence": by_confidence,
        },
        "duplicates": {
            "duplicate_groups": int(duplicate_summary.get("duplicate_groups") or 0),
            "duplicate_ads": int(duplicate_summary.get("duplicate_ads") or 0),
            "rejected_duplicates": rejected_duplicates_count,
        },
        "crawler": {
            "active_jobs": active_jobs,
            "jobs_by_status": crawl_jobs_summary,
            "latest_jobs": latest_jobs,
            "ignored_by_reason": ignored_by_reason,
        },
        "ml": ml_status,
        "outliers": {
            "price_per_mp": price_per_mp_outliers,
        },
        "issues": issues,
    }
