"""Verify deployed Studionet source against the committed contract bytes.

No wallet, credentials or third-party Python packages are required.
"""
import base64
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def rpc(endpoint, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1,
                       "method": method, "params": params}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body,
                                     headers={"Content-Type": "application/json",
                                              "Accept": "application/json",
                                              "User-Agent": "ContractAuditVerdict-SourceVerifier/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(json.dumps(result["error"]))
    return result["result"]


def main():
    evidence = json.loads((ROOT / "evidence/deployment.json").read_text())
    address = evidence["contract_address"]
    endpoint = evidence["rpc_url"]
    source = (ROOT / "contracts/contract_audit_verdict.py").read_bytes()
    expected = evidence["source_sha256"]
    local_hash = hashlib.sha256(source).hexdigest()
    if local_hash != expected:
        raise SystemExit("Local source differs from the recorded deployment hash")
    chain_id = int(rpc(endpoint, "eth_chainId", []), 16)
    if chain_id != 61999:
        raise SystemExit("RPC is not Studionet (expected chain ID 61999)")
    # Hosted Studio uses the address-only code request parameter.
    encoded = rpc(endpoint, "gen_getContractCode", [address])
    deployed_source = base64.b64decode(encoded, validate=True)
    deployed_hash = hashlib.sha256(deployed_source).hexdigest()
    github_request = urllib.request.Request(
        evidence["raw_source_url"],
        headers={"User-Agent": "ContractAuditVerdict-SourceVerifier/1.0"})
    with urllib.request.urlopen(github_request, timeout=30) as response:
        github_source = response.read()
    if github_source != source:
        raise SystemExit("MISMATCH: pinned GitHub source differs from the local file")
    if deployed_source != source:
        raise SystemExit("MISMATCH: deployed source differs from the local file")
    print("Network: studionet (61999)")
    print("Contract:", address)
    print("Source commit:", evidence["source_commit"])
    print("SHA-256:", deployed_hash)
    print("MATCH: deployed, pinned GitHub and local source are byte-for-byte identical")
    return {"chain_id": chain_id, "contract_address": address,
            "source_sha256": deployed_hash, "byte_for_byte_match": True}


if __name__ == "__main__":
    main()
