terraform {
  required_version = ">= 1.2.7"

  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "~> 0.13"
    }
    elasticstack = {
      source  = "elastic/elasticstack"
      version = "~> 0.16"
    }
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.100"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = ">= 2.47"
    }
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
  }
}

provider "ec" {}
provider "elasticstack" {}

provider "aws" {
  region = var.aws_region
}

provider "azurerm" {
  features {}
  subscription_id = var.azure_subscription_id != "" ? var.azure_subscription_id : null
  tenant_id       = var.azure_tenant_id != "" ? var.azure_tenant_id : null
  client_id       = var.azure_client_id != "" ? var.azure_client_id : null
  client_secret   = var.azure_client_secret != "" ? var.azure_client_secret : null
}

provider "azuread" {
  tenant_id     = var.azure_tenant_id != "" ? var.azure_tenant_id : null
  client_id     = var.azure_client_id != "" ? var.azure_client_id : null
  client_secret = var.azure_client_secret != "" ? var.azure_client_secret : null
}

provider "google" {
  project     = var.google_cloud_project != "" ? var.google_cloud_project : null
  region      = var.google_cloud_region
  credentials = var.google_cloud_credentials_file != "" ? file(var.google_cloud_credentials_file) : null
}
