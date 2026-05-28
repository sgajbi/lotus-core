CA_BUNDLE_A_TRANSACTION_TYPES = {
    "SPIN_OFF",
    "SPIN_IN",
    "DEMERGER_OUT",
    "DEMERGER_IN",
    "CASH_CONSIDERATION",
}
CA_BUNDLE_A_SOURCE_OUT_TYPES = {"SPIN_OFF", "DEMERGER_OUT"}
CA_BUNDLE_A_TARGET_IN_TYPES = {"SPIN_IN", "DEMERGER_IN"}
CA_BUNDLE_A_CASH_CONSIDERATION_TYPE = "CASH_CONSIDERATION"


def normalize_ca_bundle_a_transaction_type(transaction_type: str | None) -> str:
    return str(transaction_type or "").strip().upper()
