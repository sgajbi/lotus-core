import hashlib
import uuid


def proposal_run_id_from_request_hash(request_hash: object | None) -> str:
    if request_hash and request_hash != "no_hash":
        digest = hashlib.sha256(str(request_hash).encode("utf-8")).hexdigest()[:8]
        return f"pr_{digest}"
    return f"pr_{uuid.uuid4().hex[:8]}"
