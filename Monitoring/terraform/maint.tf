terraform {
  required_version = ">= 1.0.0"

  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "0.5.0"
    }
  }
}

provider "ec" {
}

resource "ec_deployment" "monitoring-clusters" {
  for_each = toset( ["us-east-1", "us-west-1"] )
  
  name                   = "${each.key}-monitoring"

  region                 = each.key
  version                = "8.5.0"
  deployment_template_id = "aws-compute-optimized-v3"

  elasticsearch {}

}

resource "ec_deployment" "monitoring-ccs" {
  name				= "monitoring-ccs"

  region			= "aws-us-east-1"
  version			= "8.5.0"
  deployment_template_id	= "aws-compute-optimized-v3"

  elasticsearch {

    dynamic "remote_cluster" {
      for_each = ec_deployment.monitoring-clusters
      
      content {
        deployment_id = remote_cluster.value.id
        alias         = remote_cluster.value.name
        ref_id        = remote_cluster.value.elasticsearch.0.ref_id
      }
    }
  }

  kibana {}

}