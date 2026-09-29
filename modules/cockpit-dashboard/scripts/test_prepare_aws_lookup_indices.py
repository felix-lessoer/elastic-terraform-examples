import unittest

from prepare_aws_lookup_indices import (
    LOOKUP_INDICES,
    merge_properties,
    migrate_index,
)


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
                    "settings": {
                        "index": {"mode": index.get("mode", "standard")}
                    },
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


class PrepareLookupIndicesTests(unittest.TestCase):
    def test_definitions_include_joinable_snapshot_indices(self):
        self.assertIn("aws-cockpit-assets", LOOKUP_INDICES)
        self.assertIn("aws-cockpit-recommendations", LOOKUP_INDICES)
        self.assertIn("aws-cockpit-coverage", LOOKUP_INDICES)
        self.assertIn("aws-cockpit-dataset-coverage", LOOKUP_INDICES)
        self.assertIn("aws-cockpit-insight-summary", LOOKUP_INDICES)

    def test_creates_missing_lookup_index(self):
        client = FakeElasticsearch()
        status = migrate_index(
            client,
            "aws-cockpit-assets",
            LOOKUP_INDICES["aws-cockpit-assets"],
        )
        self.assertEqual(status, "created")
        self.assertEqual(client.indices["aws-cockpit-assets"]["mode"], "lookup")

    def test_migrates_documents_and_adds_required_mapping(self):
        client = FakeElasticsearch(
            {
                "aws-cockpit-assets": {
                    "mode": "standard",
                    "mappings": {
                        "properties": {"@timestamp": {"type": "date"}}
                    },
                    "documents": [{"resource": {"name": "one"}}],
                }
            }
        )
        status = migrate_index(
            client,
            "aws-cockpit-assets",
            LOOKUP_INDICES["aws-cockpit-assets"],
        )
        index = client.indices["aws-cockpit-assets"]
        self.assertEqual(status, "migrated")
        self.assertEqual(index["mode"], "lookup")
        self.assertEqual(len(index["documents"]), 1)
        self.assertEqual(
            index["mappings"]["properties"]["resource"]["properties"]["key"],
            {"type": "keyword"},
        )

    def test_existing_lookup_index_is_idempotent(self):
        client = FakeElasticsearch(
            {
                "aws-cockpit-insight-summary": {
                    "mode": "lookup",
                    "mappings": {"properties": {}},
                    "documents": [],
                }
            }
        )
        status = migrate_index(
            client,
            "aws-cockpit-insight-summary",
            LOOKUP_INDICES["aws-cockpit-insight-summary"],
        )
        self.assertEqual(status, "ready")


if __name__ == "__main__":
    unittest.main()
