# API Specification: Foundational Data Queries

This document provides the detailed technical specification for the foundational `GET` endpoints in the `query_service`.

* **Base URL:** `http://core-query.dev.lotus`
* **Error Responses:**
    * `404 Not Found`: Returned if a specific resource (e.g., a portfolio) does not exist.
    * `422 Unprocessable Entity`: The query parameters are invalid.
    * `500 Internal Server Error`: An unexpected server-side error occurred.

---

## 1. Portfolios

### Get a List of Portfolios
* **Method:** `GET`
* **Path:** `/portfolios/`
* **Description:** Retrieves a list of portfolios, with optional filters.

#### Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `portfolio_id` | string | (Optional) Filter by a single, specific portfolio ID. |
| `cif_id` | string | (Optional) Filter by the client grouping ID (CIF) to get all portfolios for a client. |
| `booking_center` | string | (Optional) Filter by booking center. |

---

## 2. Positions

### Get Latest Positions for a Portfolio
* **Method:** `GET`
* **Path:** `/portfolios/{portfolio_id}/positions`
* **Description:** Retrieves the single latest daily snapshot for each security with a non-zero quantity in a given portfolio.

### Get Position History for a Security
* **Method:** `GET`
* **Path:** `/portfolios/{portfolio_id}/position-history`
* **Description:** Retrieves the time series of position history for a specific security within a portfolio.

#### Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `security_id` | string | **Required.** The unique identifier for the security to query. |
| `start_date` | string | (Optional) The start date for the date range filter (`YYYY-MM-DD`). |
| `end_date` | string | (Optional) The end date for the date range filter (`YYYY-MM-DD`). |

---

## 3. Transactions

### Get Transactions for a Portfolio
* **Method:** `GET`
* **Path:** `/portfolios/{portfolio_id}/transactions`
* **Description:** Retrieves a paginated and filterable list of transactions for a portfolio.

#### Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `security_id` | string | (Optional) Filter by a specific security ID. |
| `start_date` | string | (Optional) The start date for the date range filter (`YYYY-MM-DD`). |
| `end_date` | string | (Optional) The end date for the date range filter (`YYYY-MM-DD`). |
| `skip` | integer | (Optional, Default: 0) Number of records to skip for pagination. |
| `limit` | integer | (Optional, Default: 100) Maximum number of records to return. |
| `sort_by` | string | (Optional, Default: `transaction_date`) Field to sort by. Allowed values: `transaction_date`, `quantity`, `price`, `gross_transaction_amount`. |
| `sort_order` | string | (Optional, Default: `desc`) Sort order: `asc` or `desc`. |

---

## 4. Instruments

### Get a List of Instruments
* **Method:** `GET`
* **Path:** `/instruments/`
* **Description:** Retrieves a paginated and filterable list of all instruments in the system.

#### Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `security_id` | string | (Optional) Filter by a specific security ID. |
| `product_type` | string | (Optional) Filter by a specific product type (e.g., "Equity"). |
| `skip` | integer | (Optional, Default: 0) Number of records to skip for pagination. |
| `limit` | integer | (Optional, Default: 100) Maximum number of records to return. |

---

## 5. Market Prices

### Get Market Prices for a Security
* **Method:** `GET`
* **Path:** `/prices/`
* **Description:** Retrieves a list of historical market prices for a single security.

#### Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `security_id` | string | **Required.** The unique identifier for the security to query. |
| `start_date` | string | (Optional) The start date for the date range filter (`YYYY-MM-DD`). |
| `end_date` | string | (Optional) The end date for the date range filter (`YYYY-MM-DD`). |

---

## 6. FX Rates

### Get FX Rates for a Currency Pair
* **Method:** `GET`
* **Path:** `/fx-rates/`
* **Description:** Retrieves a list of historical foreign exchange rates for a currency pair.

#### Query Parameters
| Parameter | Type | Description |
| :--- | :--- | :--- |
| `from_currency` | string | **Required.** The base currency (e.g., "USD"). |
| `to_currency` | string | **Required.** The quote currency (e.g., "SGD"). |
| `start_date` | string | (Optional) The start date for the date range filter (`YYYY-MM-DD`). |
| `end_date` | string | (Optional) The end date for the date range filter (`YYYY-MM-DD`). |
