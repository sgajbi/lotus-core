"""Governed tenant identities for tests and local deterministic fixtures."""

from portfolio_common.domain.tenant import TenantContext, TenantId

TEST_TENANT_ID = "tenant-test"
TEST_LEGAL_BOOK_ID = "book-test"
TEST_TENANT_HEADERS = {"X-Tenant-Id": TEST_TENANT_ID}
TEST_TENANT_CONTEXT = TenantContext(tenant_id=TenantId(TEST_TENANT_ID))
