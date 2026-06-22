from .database import get_connection


JOB_COUNTER_FIELDS = {
    "pages_discovered",
    "ads_discovered",
    "ads_processed",
    "ads_inserted",
    "ads_updated",
    "error_count",
    "blocked_count",
}


def update_job(job_id: int, finished: bool = False, **fields):
    if not fields and not finished:
        return

    conn = get_connection()
    cursor = conn.cursor()

    assignments = []
    values = []

    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        values.append(value)

    if finished:
        assignments.append("finished_at = CURRENT_TIMESTAMP")

    query = f"""
        UPDATE crawl_jobs
        SET {", ".join(assignments)}
        WHERE id = ?
    """
    values.append(job_id)

    cursor.execute(query, values)
    conn.commit()
    conn.close()


def increment_job_field(job_id: int, field_name: str, amount: int = 1):
    if field_name not in JOB_COUNTER_FIELDS:
        raise ValueError(f"Camp nepermis pentru incrementare: {field_name}")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"""
        UPDATE crawl_jobs
        SET {field_name} = COALESCE({field_name}, 0) + ?
        WHERE id = ?
        """,
        (amount, job_id),
    )

    conn.commit()
    conn.close()


def is_cancel_requested(job_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT cancel_requested FROM crawl_jobs WHERE id = ?",
        (job_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False

    return bool(row["cancel_requested"])


def resolve_crawl_limits(mode: str, max_pages: int | None, max_ads: int | None):
    if mode == "quick_refresh":
        return (
            max_pages if max_pages is not None else 5,
            max_ads if max_ads is not None else 120,
        )

    if mode == "deep_crawl":
        return (
            max_pages if max_pages is not None else 40,
            max_ads if max_ads is not None else 1000,
        )

    if mode == "backfill":
        return (
            max_pages if max_pages is not None else 80,
            max_ads if max_ads is not None else 2000,
        )

    return (
        max_pages if max_pages is not None else 5,
        max_ads if max_ads is not None else 100,
    )


def should_stop_early(mode: str, consecutive_duplicate_pages: int) -> bool:
    if mode == "quick_refresh":
        return consecutive_duplicate_pages >= 2

    if mode == "deep_crawl":
        return consecutive_duplicate_pages >= 4

    if mode == "backfill":
        return False

    return consecutive_duplicate_pages >= 2
