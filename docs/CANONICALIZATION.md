# North Standard Canonicalization — NSCJ-0.1

Settlement-critical hashes must be identical across implementations. North Standard therefore defines a deliberately small canonical JSON profile for v0.1 rather than hashing implementation-native structs.

## Canonicalization rules

For supported JSON values:

1. input is UTF-8 JSON;
2. object keys are sorted lexicographically;
3. no insignificant whitespace is emitted;
4. strings preserve UTF-8 and escape JSON control characters deterministically;
5. booleans and `null` use lowercase JSON literals;
6. integers use base-10 with no leading zeroes;
7. finite floating-point values use Python-compatible shortest round-trip formatting;
8. `NaN` and infinities are invalid;
9. duplicate object keys are rejected by the C++ parser;
10. hashes are lowercase SHA-256 over the canonical UTF-8 bytes.

The Python reference uses `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. The C++20 implementation reproduces this profile for the supported v0.1 JSON domain and is differential-tested against shared vectors.

## Cross-language commitments

Three hashes matter at the language boundary:

```text
contract_hash
  = SHA256(canonical_json(compute_contract))

evidence_bundle_root
  = SHA256(canonical_json(evidence_bundle))

settlement_hash
  = SHA256(canonical_json(settlement_commitment))
```

The settlement commitment intentionally excludes implementation-specific audit metadata and diagnostic metrics. It commits to:

- contract ID;
- session ID;
- verifier policy ID;
- evidence-bundle root;
- claim states and reason codes;
- overall `ACCEPT | REJECT | INCONCLUSIVE` decision and reason codes.

This means Python and C++ may expose different build identifiers or diagnostic details while still producing the same financial authorization commitment.

## Unknown payload fields

The C++ evidence model preserves payload fields it does not interpret in an `extra` map. This is important: an unrecognized field may be irrelevant to the current verifier policy, but it still belongs to the evidence bytes being committed.

Unknown must not mean dropped.

## Wire ingestion

The C++ CLI accepts a shared JSON object:

```json
{
  "contract": { "...": "..." },
  "evidence_bundle": { "...": "..." }
}
```

and exposes:

```bash
north-standard-cpp verify-json < wire.json
```

The result prints:

```text
contract_hash|evidence_bundle_root|settlement_hash|decision|reason_codes
```

CI generates this wire input from the Python reference scenarios, sends the exact JSON through the C++ parser and verifier, and requires all five outputs to match the Python reference.

## Scope

NSCJ-0.1 is a hackathon/research protocol profile, not a claim of general RFC 8785/JCS conformance. If North Standard later adopts a standards-defined canonical representation, that will require a new versioned hashing profile rather than silently changing existing contract semantics.
