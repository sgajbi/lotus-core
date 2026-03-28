from __future__ import annotations


COUNTRY_TO_REGION = {
    "US": "North America",
    "CA": "North America",
    "MX": "Latin America",
    "BR": "Latin America",
    "AR": "Latin America",
    "GB": "Europe",
    "IE": "Europe",
    "FR": "Europe",
    "DE": "Europe",
    "CH": "Europe",
    "IT": "Europe",
    "ES": "Europe",
    "NL": "Europe",
    "SE": "Europe",
    "NO": "Europe",
    "DK": "Europe",
    "FI": "Europe",
    "AT": "Europe",
    "BE": "Europe",
    "PT": "Europe",
    "SG": "Asia Pacific",
    "HK": "Asia Pacific",
    "CN": "Asia Pacific",
    "JP": "Asia Pacific",
    "AU": "Asia Pacific",
    "NZ": "Asia Pacific",
    "IN": "Asia Pacific",
    "KR": "Asia Pacific",
    "TW": "Asia Pacific",
    "TH": "Asia Pacific",
    "MY": "Asia Pacific",
    "ID": "Asia Pacific",
    "PH": "Asia Pacific",
    "VN": "Asia Pacific",
    "AE": "Middle East & Africa",
    "SA": "Middle East & Africa",
    "ZA": "Middle East & Africa",
    "EG": "Middle East & Africa",
    "NG": "Middle East & Africa",
}


def resolve_region(country_code: str | None) -> str | None:
    if not country_code:
        return None
    return COUNTRY_TO_REGION.get(country_code.upper(), "Other")
