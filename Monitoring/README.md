# Create Elastic Cloud Monitoring Clusters

This example creates one Monitoring Cluster per region. Those clusters can be used to collect the metrics of the Elastic Cloud Elasticsearch Clusters that you are running.
At the moment Elastic needs to collect the monitoring data within the same cluster or within a cluster that is in the same region. Having the monitoring data in a separate cluster is best practice. 
In order to get the full overview accross all Elastic Cloud Clusters this script also creates a master cluster that leverages Cross Cluster Search (CCS) to get access to all monitoring data. 
All of that happens within the script.

## Get started

You need to create an Elastic Cloud API Key and make it available for terraform using an environment variable. 

In addition to that you need to set the regions where you have clusters deployed within the main.tf script. 

