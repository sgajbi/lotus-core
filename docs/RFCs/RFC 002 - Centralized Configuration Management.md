RFC-001: Centralized Configuration Management
1. Summary

This RFC proposes the implementation of a centralized and schema-validated configuration system for all microservices within the portfolio analytics platform. The current approach, while functional, relies on a mix of environment variables and disparate configurations within each service. This proposal aims to unify this by introducing a shared, validated configuration model that will be loaded at runtime.

2. Problem Statement

The decentralized nature of the current configuration management presents several challenges:

Inconsistency: Each service manages its configuration independently, leading to potential inconsistencies in naming conventions, validation logic, and default values.

Lack of Validation: There is no consistent, system-wide mechanism to validate configurations at startup. This can lead to services starting in an invalid state, only to fail later at runtime.

Maintainability: As the system grows, managing a growing number of environment variables and configuration files across multiple services becomes increasingly complex and error-prone.

Observability: It is difficult to get a holistic view of the system's configuration at any given time, which complicates debugging and operational oversight.

3. Proposed Solution

We will implement a centralized configuration management system with the following key features:

Pydantic-based Configuration Models: Each service will define its configuration using a Pydantic BaseSettings model. This will provide automatic validation, type casting, and clear documentation of all required and optional configuration parameters.

Shared Configuration Library: A new shared library, portfolio-config, will be created within the src/libs directory. This library will contain base configuration models and helper functions that can be extended by individual services.

Centralized Loading: Each service will load its configuration from a unified source (e.g., environment variables, .env file) into its respective Pydantic model at startup. This ensures that all configurations are validated before any business logic is executed.

Strict Startup Validation: Services will fail fast at startup if their configuration does not match the defined schema. This prevents services from running in a partially configured or invalid state.

4. High-Level Plan

Create a portfolio-config shared library: This will house the base configuration models and utilities.

Refactor ingestion_service: This will be the first service to be migrated to the new configuration system as a proof-of-concept.

Update docker-compose.yml: Ensure that the new library is correctly mounted and available to all services.

Gradual Rollout: Sequentially refactor all other services to use the new centralized configuration system.

5. Acceptance Criteria

All services load their configuration via Pydantic models.

Services fail at startup if their configuration is invalid.

Configuration is consistent and easily manageable across the entire system.

The README.md is updated to reflect the new configuration management approach.