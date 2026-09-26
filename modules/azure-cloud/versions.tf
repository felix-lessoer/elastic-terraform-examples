terraform {
  required_version = ">= 1.2.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.100"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = ">= 2.47"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5"
    }
  }
}
