from __future__ import annotations

from compras_crawler.normalize import extract_records, normalize_record, stable_hash, stable_json


def test_extract_records_reads_common_resultado_wrapper():
    assert extract_records({"resultado": [{"codigoUasg": 1}]}) == [{"codigoUasg": 1}]
    assert extract_records([{"codigoUasg": 2}]) == [{"codigoUasg": 2}]


def test_normalize_record_uses_alias_key_and_stable_payload_hash():
    record = {"codigoUasg": 123, "nomeUasg": "ALPHA"}

    normalized = normalize_record(
        entity_name="uasg",
        record=record,
        key_fields=("codigoUasg", "codigo_uasg"),
        run_id="run-1",
        source_job="uasg_status_true",
        source_page=1,
    )

    assert normalized["entity_name"] == "uasg"
    assert normalized["record_key"] == "123"
    assert normalized["payload_json"] == stable_json(record)
    assert normalized["payload_hash"] == stable_hash(record)
    assert normalized["run_id"] == "run-1"
    assert normalized["source_page"] == 1
