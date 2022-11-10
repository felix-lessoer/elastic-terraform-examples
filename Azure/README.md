# Azure environment

```json
{
	"azure_region" : "eu-west-2",	 
	"azure_client_id" : "<YOUR CLIENT ID>",
	"azure_client_secret" : "<YOUR CLIENT SECRET>",
	"azure_tenant_id": "<YOUR TENANT ID>",
	"azure_subscription_id": "<YOUR SUBSCRIPTION ID>"
}
```

List of other optional parameters that can be added to terraform.tfvars.json 
| Parameter Name  | Default value | Example | Description |
| ------------- | ------------- | ------------- | ------------- |
| elastic_version  | latest  | 8.4.1  | Used to define the Elastic Search version  |
| elastic_region  | azure-westeurope  | azure-westeurope | Used to set the Elastic Cloud region for the Azure deployment  |
| elastic_deployment_name  | Azure Observe and Protect  | Azure Observe and Protect  | Used to define the name for the Elastic deployment  |


#### Create Azure Access credentials

1. Visit the [Azure Active Directory](https://portal.azure.com/#view/Microsoft_AAD_IAM/ActiveDirectoryMenuBlade/~/RegisteredApps) config page in Azure
2. Create a new application
3. Click on "Client credentials"
4. Click on "New client secret" and save the credentials in your `azure.json` file

Hint: The credentials you choose here will also be used to authenticate the Elastic Agent against your Azure Environment. In production ready setups you might want to change that. Elastic also offers other authentication mechanisms for the Elastic Agent. This terraform script does not ATM.


 
