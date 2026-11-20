from __future__ import annotations

import calendar
import csv
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
import requests


def get_epc_certificates(
    cert_type: str,
    month_date: str | date | datetime,
    bearer_token: str,
    end_date: str | date | datetime | None = None,
    *,
    postcode: str | None = None,
    uprn: str | int | None = None,
    address: str | None = None,
    councils: Sequence[str] | None = None,
    constituencies: Sequence[str] | None = None,
    efficiency_ratings: Sequence[str] | None = None,
    page_size: int = 5000,
    output_file: str | Path | None = None,
    max_retries: int = 3,
    timeout: int = 60,
) -> list[dict[str, Any]]:
    """
    Fetch domestic ('dom') or non-domestic ('non-dom') EPC certificates for a specific month
    or month range (when `end_date` is provided), iterating through all paginated results
    and optionally saving to a CSV or JSON file.
    """
    endpoint_map = {
        "dom": "/api/domestic/search",
        "domestic": "/api/domestic/search",
        "non-dom": "/api/non-domestic/search",
        "non_dom": "/api/non-domestic/search",
        "nondom": "/api/non-domestic/search",
        "non-domestic": "/api/non-domestic/search",
        "non_domestic": "/api/non-domestic/search",
    }

    normalized_type = cert_type.strip().lower()
    if normalized_type not in endpoint_map:
        raise ValueError(
            f"Invalid cert_type '{cert_type}'. Expected 'dom' ('domestic') or 'non-dom' ('non-domestic')."
        )

    if not bearer_token or not bearer_token.strip():
        raise ValueError("A valid bearer_token must be provided.")

    if not (1 <= page_size <= 5000):
        raise ValueError("page_size must be between 1 and 5000.")

    def _extract_year_month(val: str | date | datetime, param_name: str) -> tuple[int, int]:
        if isinstance(val, (datetime, date)):
            return val.year, val.month
        if isinstance(val, str):
            cleaned = val.strip()
            for fmt in ("%Y-%m", "%Y-%m-%d", "%Y/%m", "%m/%Y", "%B %Y", "%b %Y"):
                try:
                    parsed_dt = datetime.strptime(cleaned, fmt)
                    return parsed_dt.year, parsed_dt.month
                except ValueError:
                    continue
            raise ValueError(
                f"Invalid {param_name} format '{val}'. Expected 'YYYY-MM' (e.g. '2023-05') "
                "or 'YYYY-MM-DD' (e.g. '2023-05-01')."
            )
        raise TypeError(f"{param_name} parameter must be a string, datetime.date, or datetime.datetime.")

    # Parse start month (1st of month_date)
    start_year, start_month = _extract_year_month(month_date, "month_date")
    first_day = date(start_year, start_month, 1)

    # Parse end month (end of end_date's month, or end of month_date's month if blank/None)
    if end_date is None or (isinstance(end_date, str) and not end_date.strip()):
        end_year, end_month = start_year, start_month
    else:
        end_year, end_month = _extract_year_month(end_date, "end_date")

    _, last_day_num = calendar.monthrange(end_year, end_month)
    last_day = date(end_year, end_month, last_day_num)

    if last_day < first_day:
        raise ValueError(
            f"end_date ({last_day.isoformat()}) cannot be earlier than month_date ({first_day.isoformat()})."
        )

    today = date.today()
    if first_day >= today:
        raise ValueError(
            f"Requested start month ({first_day.strftime('%Y-%m')}) cannot start on or after "
            f"today's date ({today.isoformat()}). The API does not allow today's or future dates."
        )
    if last_day >= today:
        last_day = today - timedelta(days=1)

    date_start, date_end = first_day.isoformat(), last_day.isoformat()
    url = f"https://api.get-energy-performance-data.communities.gov.uk{endpoint_map[normalized_type]}"

    clean_token = bearer_token.strip()
    if clean_token.lower().startswith("bearer "):
        clean_token = clean_token[7:].strip()

    headers = {
        "Authorization": f"Bearer {clean_token}",
        "Accept": "application/json",
    }

    base_params: dict[str, Any] = {
        "date_start": date_start,
        "date_end": date_end,
        "page_size": page_size,
    }

    if postcode:
        base_params["postcode"] = postcode.strip()
    if uprn is not None:
        base_params["uprn"] = str(uprn).strip().zfill(12)
    if address:
        base_params["address"] = address.strip()
    if councils:
        base_params["council[]"] = list(councils)
    if constituencies:
        base_params["constituency[]"] = list(constituencies)
    if efficiency_ratings:
        base_params["efficiency_rating[]"] = [r.strip().upper() for r in efficiency_ratings]

    all_certificates: list[dict[str, Any]] = []
    current_page = 1

    with requests.Session() as session:
        session.headers.update(headers)

        while True:
            params = {**base_params, "current_page": current_page}

            for attempt in range(max_retries + 1):
                response = session.get(url, params=params, timeout=timeout)

                if response.status_code == 429:
                    if attempt < max_retries:
                        retry_after = int(response.headers.get("Retry-After", 10 * (attempt + 1)))
                        time.sleep(retry_after)
                        continue
                    response.raise_for_status()

                break

            if response.status_code == 404:
                break

            if response.status_code == 400:
                try:
                    err_detail = response.json()
                except ValueError:
                    err_detail = response.text
                raise ValueError(f"Bad Request (400) from EPC API: {err_detail}")

            response.raise_for_status()

            payload = response.json()
            page_data = payload.get("data", [])
            if isinstance(page_data, list):
                all_certificates.extend(page_data)

            pagination = payload.get("pagination", {})
            total_pages = pagination.get("totalPages", 1)
            next_page = pagination.get("nextPage")

            if next_page is not None:
                current_page = int(next_page)
            elif current_page < total_pages:
                current_page += 1
            else:
                break

    if output_file is not None:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.suffix.lower() == ".json":
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(all_certificates, f, indent=2, ensure_ascii=False)
        else:
            with output_path.open("w", newline="", encoding="utf-8") as f:
                if all_certificates:
                    fieldnames = list(all_certificates[0].keys())
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(all_certificates)
                else:
                    f.write("")

    return all_certificates




