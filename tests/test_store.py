from __future__ import annotations

import json
from datetime import timedelta

import pytest

from conftest import NOW, make_job
from jobradar.store import DynamoStore, FileStore


def test_file_store_round_trip_and_expiry(tmp_path):
    path = tmp_path / "state" / "seen.json"
    store = FileStore(path, ttl_days=30)
    assert store.seen_keys(["greenhouse:acme:1"]) == set()

    store.mark_seen([make_job(job_id="1")], NOW - timedelta(days=40))
    store.mark_seen([make_job(job_id="2")], NOW)

    data = json.loads(path.read_text())
    assert set(data["seen"]) == {"greenhouse:acme:2"}  # the 40-day-old entry expired
    assert store.seen_keys(["greenhouse:acme:1", "greenhouse:acme:2"]) == {"greenhouse:acme:2"}


class FakeDynamo:
    def __init__(self, unprocessed_reads=0, unprocessed_writes=0):
        self.items: dict[str, dict] = {}
        self.get_calls = 0
        self.write_calls = 0
        self._unprocessed_reads = unprocessed_reads
        self._unprocessed_writes = unprocessed_writes

    def batch_get_item(self, RequestItems):
        self.get_calls += 1
        [(table, request)] = RequestItems.items()
        assert len(request["Keys"]) <= 100
        keys = [key["job_key"]["S"] for key in request["Keys"]]
        if self._unprocessed_reads:
            self._unprocessed_reads -= 1
            return {"Responses": {table: []}, "UnprocessedKeys": RequestItems}
        found = [{"job_key": {"S": key}} for key in keys if key in self.items]
        return {"Responses": {table: found}, "UnprocessedKeys": {}}

    def batch_write_item(self, RequestItems):
        self.write_calls += 1
        [(_table, requests)] = RequestItems.items()
        assert len(requests) <= 25
        if self._unprocessed_writes:
            self._unprocessed_writes -= 1
            return {"UnprocessedItems": RequestItems}
        for request in requests:
            item = request["PutRequest"]["Item"]
            self.items[item["job_key"]["S"]] = item
        return {"UnprocessedItems": {}}


def test_dynamo_store_batches_and_retries():
    client = FakeDynamo(unprocessed_reads=1, unprocessed_writes=1)
    store = DynamoStore("seen", client=client, sleep=lambda _: None, ttl_days=10)
    jobs = [make_job(job_id=str(n)) for n in range(60)]

    store.mark_seen(jobs, NOW)
    assert client.write_calls == 4  # 3 batches of up to 25, one retried
    item = client.items["greenhouse:acme:0"]
    assert item["expires_at"]["N"] == str(int(NOW.timestamp()) + 10 * 86_400)

    keys = [job.key for job in jobs] + [f"greenhouse:acme:new-{n}" for n in range(60)]
    assert store.seen_keys(keys) == {job.key for job in jobs}
    assert client.get_calls == 3  # 2 batches of up to 100, one retried


def test_dynamo_store_deduplicates_keys_in_a_batch():
    client = FakeDynamo()
    DynamoStore("seen", client=client).mark_seen([make_job(), make_job()], NOW)
    assert len(client.items) == 1


def test_dynamo_store_gives_up_eventually():
    client = FakeDynamo(unprocessed_writes=99)
    store = DynamoStore("seen", client=client, sleep=lambda _: None, max_attempts=3)
    with pytest.raises(RuntimeError, match="unprocessed items"):
        store.mark_seen([make_job()], NOW)
