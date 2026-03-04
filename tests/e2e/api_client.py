# tests/e2e/api_client.py
import requests
import time
import pytest
from typing import List, Dict, Any, Callable
from requests.exceptions import RequestException

class E2EApiClient:
    """A client for interacting with the system's APIs in E2E tests."""
    def __init__(self, ingestion_url: str, query_url: str):
        self.ingestion_url = ingestion_url
        self.query_url = query_url
        self.session = requests.Session()

    def ingest(self, endpoint: str, payload: Dict[str, List[Dict[str, Any]]]) -> requests.Response:
        """Sends data to a specified ingestion endpoint."""
        url = f"{self.ingestion_url}{endpoint}"
        response = self.session.post(url, json=payload, timeout=10)
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
        url = f"{self.query_url}{endpoint}"
        response = self.session.post(url, json=payload, timeout=20)
        if raise_for_status:
            response.raise_for_status()
        return response

    def poll_for_data(
        self,
        endpoint: str,
        validation_func: Callable[[Any], bool],
        timeout: int = 60,
        interval: int = 2,
        fail_message: str = "Polling timed out"
    ):
        """Polls a query endpoint until the validation function returns True."""
        start_time = time.time()
        last_response_data = None
        while time.time() - start_time < timeout:
            try:
                response = self.query(endpoint)
                if response.status_code == 200:
                    last_response_data = response.json()
                    if validation_func(last_response_data):
                        return last_response_data
            except RequestException:
                pass  # Ignore connection errors during polling
            time.sleep(interval)
        
        pytest.fail(
            f"{fail_message} after {timeout} seconds for endpoint {endpoint}. "
            f"Last response: {last_response_data}"
        )
