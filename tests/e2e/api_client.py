# tests/e2e/api_client.py
import re
import time
from typing import Any, Callable, Dict, List

import pytest
import requests
from requests.exceptions import RequestException


class E2EApiClient:
    """A client for interacting with the system's APIs in E2E tests."""

    def __init__(self, ingestion_url: str, query_url: str, query_control_plane_url: str):
        self.ingestion_url = ingestion_url
        self.query_url = query_url
        self.query_control_plane_url = query_control_plane_url
        self.session = requests.Session()

    @staticmethod
    def _camel_to_snake(value: str) -> str:
        if "_" in value:
            return value
        step1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", step1).lower()

    @classmethod
    def _canonical_key(cls, key: str) -> str:
        normalized = cls._camel_to_snake(key)
        legacy_alias_map = {
            "cif_id": "client_id",
            "booking_center": "booking_center_code",
            "instrument_currency": "currency",
        }
        return legacy_alias_map.get(normalized, normalized)

    @classmethod
    def _normalize_payload_keys(cls, data: Any) -> Any:
        """Recursively normalize payload keys to snake_case for canonical ingestion APIs."""
        if isinstance(data, dict):
            return {
                cls._canonical_key(str(key)): cls._normalize_payload_keys(value)
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [cls._normalize_payload_keys(item) for item in data]
        return data

    def ingest(self, endpoint: str, payload: Dict[str, List[Dict[str, Any]]]) -> requests.Response:
        """Sends data to a specified ingestion endpoint."""
        url = f"{self.ingestion_url}{endpoint}"
        normalized_payload = self._normalize_payload_keys(payload)
        response = self.session.post(url, json=normalized_payload, timeout=10)
        response.raise_for_status()
        return response

    def reprocess_transactions(self, transaction_ids: List[str]) -> requests.Response:
        """Queues existing transactions for replay through the governed reprocessing API."""
        url = f"{self.ingestion_url}/reprocess/transactions"
        response = self.session.post(
            url,
            json={"transaction_ids": transaction_ids},
            timeout=10,
        )
        response.raise_for_status()
        return response

    def query(self, endpoint: str) -> requests.Response:
        """Retrieves data from a specified query endpoint."""
        url = f"{self.query_url}{endpoint}"
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        return response

    def post_query(
        self,
        endpoint: str,
        payload: Dict,
        *,
        raise_for_status: bool = True,
    ) -> requests.Response:
        """Sends a POST request to a specified query endpoint."""
        base_url = (
            self.query_control_plane_url
            if endpoint.startswith("/integration/")
            else self.query_url
        )
        url = f"{base_url}{endpoint}"
        response = self.session.post(url, json=payload, timeout=20)
        if raise_for_status:
            response.raise_for_status()
        return response

    def query_control(self, endpoint: str) -> requests.Response:
        """Retrieves data from a specified query control-plane endpoint."""
        url = f"{self.query_control_plane_url}{endpoint}"
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        return response

    def poll_for_data(
        self,
        endpoint: str,
        validation_func: Callable[[Any], bool],
        timeout: int = 60,
        interval: int = 2,
        fail_message: str = "Polling timed out",
    ):
        """Polls a query endpoint until the validation function returns True."""
        start_time = time.time()
        last_response_data = None
        last_error = None
        while time.time() - start_time < timeout:
            try:
                response = self.query(endpoint)
                if response.status_code == 200:
                    last_response_data = response.json()
                    if validation_func(last_response_data):
                        return last_response_data
            except RequestException as exc:
                last_error = repr(exc)
            time.sleep(interval)

        pytest.fail(
            f"{fail_message} after {timeout} seconds for endpoint {endpoint}. "
            f"Last response: {last_response_data}. Last error: {last_error}"
        )

    def poll_for_post_query_data(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        validation_func: Callable[[Any], bool],
        timeout: int = 60,
        interval: int = 2,
        fail_message: str = "Polling timed out",
    ):
        """Poll a POST-based query endpoint until the validation function returns True."""
        start_time = time.time()
        last_response_data = None
        last_status_code = None
        last_error = None
        while time.time() - start_time < timeout:
            try:
                response = self.post_query(endpoint, payload, raise_for_status=False)
                last_status_code = response.status_code
                if response.status_code == 200:
                    last_response_data = response.json()
                    if validation_func(last_response_data):
                        return last_response_data
                else:
                    last_response_data = response.text
            except RequestException as exc:
                last_error = repr(exc)
            time.sleep(interval)

        pytest.fail(
            f"{fail_message} after {timeout} seconds for endpoint {endpoint}. "
            f"Last status: {last_status_code}. Last response: {last_response_data}. "
            f"Last error: {last_error}"
        )
