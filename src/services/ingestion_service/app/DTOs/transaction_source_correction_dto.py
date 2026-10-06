"""Named HTTP schema backed by the shared signed-command input contract."""

from portfolio_common.api_contract.async_commands import SourceEvidenceConfirmationInput


class TransactionSourceCorrectionRequest(SourceEvidenceConfirmationInput):
    """Evidence-only confirmation; persisted scope and grants remain server-owned."""
