### RFC 015: Hyper-Personalization via Client Profile Enrichment

  * **Status**: Proposed
  * **Date**: 2025-08-30
  * **Services Affected**: `ingestion-service`, `persistence-service`, `portfolio-common`, `query-service`, `nba-service`, `insight-report-service`
  * **Related RFCs**: RFC 011, RFC 009

-----

## 1\. Summary (TL;DR)

This RFC proposes a significant enhancement to our data model and AI engines to enable **hyper-personalized** client recommendations and insights. We will enrich the core `Portfolio` entity with a structured `client_profile` that captures individual client goals (e.g., retirement, education), preferences (e.g., ESG focus), and constraints (e.g., restricted securities).

This deeper, qualitative context will be ingested and persisted through our existing pipeline and then consumed by the `nba-service` and `insight-report-service`. This allows our AI engines to generate recommendations and commentary that are not just financially sound, but are explicitly aligned with the client's life objectives and personal values.

-----

## 2\. Motivation

To deliver a truly "high-touch" experience at scale, our system must understand the "why" behind the numbers. A standard risk profile is not enough. By integrating a client's personal goals and values into our analytical process, we can:

  * **Generate Goal-Oriented Recommendations**: Shift from generic advice ("rebalance to target") to highly relevant suggestions ("increase savings rate by 2% to stay on track for your 2045 retirement goal").
  * **Build Deeper Trust**: Demonstrate to the end-client that their personal values (like ESG) are being actively considered in the management of their portfolio.
  * **Create a Powerful Differentiator**: Offer a level of personalization that is impossible for advisors to replicate manually across their entire book of business, creating a significant competitive advantage.

-----

## 3\. Architectural Changes & Data Flow

### 3.1. Data Model Enrichment

The core change is the addition of a new `client_profile` column to the `portfolios` table. Using a `JSONB` type provides the flexibility to evolve the profile schema over time without requiring database migrations for every new field.

**Proposed `client_profile` JSONB Schema:**

```json
{
  "goals": [
    {
      "type": "RETIREMENT", 
      "target_year": 2045, 
      "target_amount": 5000000,
      "priority": "HIGH"
    },
    {
      "type": "EDUCATION", 
      "target_year": 2035,
      "target_amount": 250000,
      "priority": "MEDIUM"
    }
  ],
  "preferences": {
    "esg_focus": "HIGH", 
    "commentary_tone": "CONCISE"
  },
  "constraints": {
    "restricted_sectors": ["TOBACCO", "GAMBLING"]
  }
}
```

### 3.2. Ingestion & Persistence

1.  **`ingestion-service`**: The `POST /ingest/portfolios` endpoint and its corresponding `Portfolio` DTO will be updated to accept the new, optional `client_profile` object.
2.  **`persistence-service`**: The `PortfolioConsumer` will be enhanced to validate and persist the `client_profile` JSONB data into the `portfolios` table.

### 3.3. Consumption by AI Services

1.  **`query-service`**: The `/portfolios/{id}` endpoint will be updated to return the enriched `client_profile` data.
2.  **`nba-service` & `insight-report-service`**: These services will now fetch the enriched portfolio data. This new context becomes a primary input for the "Signal Detection" and "Narrative Synthesis" stages of their respective pipelines.

-----

## 4\. New Hyper-Personalized Recommendation Signals

This enriched data enables a new class of powerful, high-value signals in the `nba-service`:

  * **Goal Progress Signal**: The engine can now run a simple projection to determine if the portfolio is on track to meet a stated goal. If not, it can generate a recommendation like, "Increase contribution rate to meet retirement goal."
  * **Preference Mismatch Signal**: The engine can scan the portfolio's holdings and flag any that conflict with the client's stated ESG or ethical preferences.
  * **Constraint Violation Signal**: The engine can flag any holdings that violate a hard constraint, such as an allocation to a restricted sector.
  * **Goal-Funding Recommendation**: When a goal's target date is approaching, the engine can recommend derisking the assets allocated to that specific goal.

-----

## 5\. Implementation Roadmap

  * **Phase 1: Foundational Data Layer**:
      * Implement the Alembic migration to add the `client_profile` column to the `portfolios` table.
      * Update the ingestion and persistence services to handle the new data.
      * Update the `query-service` to expose the enriched profile.
  * **Phase 2: Integration with NBA Engine**:
      * Enhance the `nba-service`'s Signal Detection layer to incorporate the new profile data.
      * Implement the new "Goal Progress" and "Preference Mismatch" signals.
  * **Phase 3: Integration with NLG Engine**:
      * Enhance the `insight-report-service` to use the client's goals and preferences to generate more personalized, empathetic narrative commentary.
 

 