mock_provider "google" {
  mock_resource "google_service_account" {
    defaults = {
      email = "collector@example-project-123.iam.gserviceaccount.com"
      name  = "projects/example-project-123/serviceAccounts/collector@example-project-123.iam.gserviceaccount.com"
    }
  }

  mock_resource "google_logging_project_sink" {
    defaults = {
      writer_identity = "serviceAccount:logging@example-project-123.iam.gserviceaccount.com"
    }
  }
}

mock_provider "random" {
  mock_resource "random_id" {
    defaults = {
      hex = "abcdef"
    }
  }
}

variables {
  project_id = "example-project-123"
  company_labels = {
    owner = "platform"
  }
}

run "default_paths_remain_module_owned" {
  command = plan

  assert {
    condition     = length(output.topic_names) == 5 && length(output.subscription_names) == 5
    error_message = "Default configuration must still create all five collection paths."
  }

  assert {
    condition = alltrue([
      for ownership in values(output.collection_ownership) :
      ownership.topic == "module" &&
      ownership.sink == "module" &&
      ownership.subscription == "module"
    ])
    error_message = "Default collection resources must remain module-owned."
  }
}

run "duplicate_existing_topics_are_rejected" {
  command = plan

  variables {
    existing_topic_names = {
      audit    = "shared-topic"
      firewall = "shared-topic"
    }
  }

  expect_failures = [check.existing_path_uniqueness]
}

run "existing_sink_requires_existing_topic" {
  command = plan

  variables {
    existing_sink_names = {
      audit = "customer-audit-sink"
    }
  }

  expect_failures = [check.existing_path_dependencies]
}
