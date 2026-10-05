import unittest

from prepare_gcp_lookup_indices import LOOKUP_INDICES, merge_properties, migrate_index


class FakeElasticsearch:
    def __init__(self, indices=None):
        self.indices = indices or {}

    def request(self, method, path, body=None, *, allow_not_found=False):
        name = path.split("/")[0]
        if method == "GET" and path.endswith("/_count"):
            return {"count": len(self.indices[name]["documents"])}
        if method == "GET":
            if name not in self.indices:
                return None if allow_not_found else {}
            index = self.indices[name]
            return {
                name: {
                    "settings": {"index": {"mode": index.get("mode", "standard")}},
                    "mappings": index.get("mappings", {"properties": {}}),
                }
            }
        if method == "PUT" and path.endswith("/_mapping"):
            self.indices[name]["mappings"]["properties"] = merge_properties(
                self.indices[name]["mappings"].get("properties", {}),
                body["properties"],
            )
            return {}
        if method == "PUT":
            self.indices[name] = {
                "mode": body["settings"]["index.mode"],
                "mappings": body["mappings"],
                "documents": [],
            }
            return {}
        if method == "DELETE":
            del self.indices[name]
            return {}
        if method == "POST" and path.startswith("_reindex"):
            source = body["source"]["index"]
            destination = body["dest"]["index"]
            self.indices[destination]["documents"] = list(
                self.indices[source]["documents"]
            )
            return {}
        raise AssertionError((method, path))


class PrepareGcpLookupIndicesTests(unittest.TestCase):
    def test_definitions_cover_all_joinable_snapshots(self):
        self.assertEqual(
            set(LOOKUP_INDICES),
            {
                "gcp-cockpit-assets",
                "gcp-cockpit-recommendations",
                "gcp-cockpit-coverage",
                "gcp-cockpit-dataset-coverage",
                "gcp-cockpit-insight-summary",
            },
        )

    def test_creates_missing_lookup_index(self):
        client = FakeElasticsearch()
        status = migrate_index(
            client, "gcp-cockpit-assets", LOOKUP_INDICES["gcp-cockpit-assets"]
        )
        self.assertEqual(status, "created")
        self.assertEqual(client.indices["gcp-cockpit-assets"]["mode"], "lookup")

    def test_migration_preserves_documents_and_adds_resource_key(self):
        client = FakeElasticsearch(
            {
                "gcp-cockpit-assets": {
                    "mode": "standard",
                    "mappings": {"properties": {"@timestamp": {"type": "date"}}},
                    "documents": [{"resource": {"name": "vm-one"}}],
                }
            }
        )
        status = migrate_index(
            client, "gcp-cockpit-assets", LOOKUP_INDICES["gcp-cockpit-assets"]
        )
        index = client.indices["gcp-cockpit-assets"]
        self.assertEqual(status, "migrated")
        self.assertEqual(index["mode"], "lookup")
        self.assertEqual(index["documents"], [{"resource": {"name": "vm-one"}}])
        self.assertEqual(
            index["mappings"]["properties"]["resource"]["properties"]["key"],
            {"type": "keyword"},
        )

    def test_existing_lookup_index_is_idempotent(self):
        client = FakeElasticsearch(
            {
                "gcp-cockpit-insight-summary": {
                    "mode": "lookup",
                    "mappings": {"properties": {}},
                    "documents": [],
                }
            }
        )
        self.assertEqual(
            migrate_index(
                client,
                "gcp-cockpit-insight-summary",
                LOOKUP_INDICES["gcp-cockpit-insight-summary"],
            ),
            "ready",
        )


if __name__ == "__main__":
    unittest.main()
