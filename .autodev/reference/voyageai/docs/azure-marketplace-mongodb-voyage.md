> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# MongoDB Voyage AI Models in Azure

Deploy MongoDB Voyage AI models using Azure Marketplace

You can use <a href="https://azuremarketplace.microsoft.com/en-us/marketplace/apps?page=1&search=mongodb%2C%20inc.%20voyage" target="_blank">Azure managed applications</a> to deploy MongoDB Voyage AI models as real-time inference API endpoints in a customer Azure account and virtual network (VNet). Azure managed applications offer the following key benefits:

1. **Data flow and access control**: Data never leaves your virtual network, addressing data privacy risks associated with third-party or multi-tenant serving.
2. **Reliability and compliance backed by Azure**: Azure serves as your sole sub-processor, so you inherit all of Azure's reliability and compliance guarantees.
3. **Billing and payment through Azure**: By using your existing Azure billing information and credits to purchase MongoDB Voyage AI models, you don't need to manage a separate third-party payment and billing system.

# Available Models

To see which models you can deploy, search for "Voyage AI by MongoDB" in [Azure Marketplace](https://azuremarketplace.microsoft.com/en-us/marketplace/apps?page=1\&search=mongodb%2C%20inc.%20voyage) .

# Pricing

Azure managed applications using MongoDB Voyage AI models are billed hourly. The total hourly cost is the sum of the virtual machine (VM) price ($5 per hour) and the price of the underlying instance in your region. There is no management cost for this managed Azure application, which is why the listed Azure managed application monthly price is $0.

# Prerequisites

To deploy a MongoDB Voyage Azure managed application, you must have the following:

* An existing <a href="https://learn.microsoft.com/en-us/microsoft-365/enterprise/subscriptions-licenses-accounts-and-tenants-for-microsoft-cloud-offerings?view=o365-worldwide#subscriptions" target="_blank">Azure subscription</a>.
* An existing virtual network to deploy a MongoDB Voyage Azure managed application. For instructions, see the **[Create a Virtual Network](#create-a-virtual-network)** section.
* Sufficient GPU vCPU quota for the instance family required by
  your chosen Voyage Azure managed application. To learn how to check your quota or request a quota increase, see the **[Quota](#quota)** section.

If you meet all the prerequisites, skip to the \*\*[Create a MongoDB Voyage API endpoint in Virtual Network](#create-a-voyage-api-endpoint-in-virtual-network) \*\* section.

# Quota

This section includes guidance on how to check your quota and request an increase if necessary. If you have sufficient quota, skip this section.

## Check Quota

1. Go to **Subscriptions** in your <a href="https://portal.azure.com/" target="_blank">Azure portal</a>.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/526af4ac1a7d0826f5cd09bc7048bfbc61f4eb620a38d401335443d7572a2145-01-ba0d965becdd40c4a2fbadce985619ccf474a167b02bc437030a418b81a1c875-image.png" />

2. Select the subscription you want to use for the Azure managed application. In the following example, we select the "Pay-As-You-Go" subscription. Within your subscription page, select **Usage + quotas** under **Settings**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/9204ea20c76ff1eb90d841a1fe24f8809e1c501ed5f276ae25b712da9a5402f8-02-c8828e1c9de19b41032c0241af2c3bebd4647b3d9a50f50bd74012d4ff8e7898-image.png" />

3. Search for the GPU instance family required by your chosen. For example, `Standard_NC40ads_H100_v5` or `Standard_NC24ads_A100_v4`. Filter the **Region** for your desired region; in the example below, we filtered the region for "West US 2."

4. Ensure you have sufficient quota for the number of MongoDB Voyage Azure managed applications you want to deploy.  Search for the GPU instance family required by your chosen
   Voyage Azure managed application in the search bar. If you do not have sufficient quota, continue to the next section (**[Request Quota Increase](#request-quota-increase)**) to request more quota.

## Request Quota Increase

From the **Usage + quotas** page of your desired subscription, you can request to increase your quota:

1. Check the checkbox for the GPU instance family quota required
   by your chosen Voyage Azure managed application. Select the **New Quota Request** drop down, and select **Enter a new limit**.  A **New Quota Request** panel will appear.

<Image align="center" border={false} width="600px" src="https://files.readme.io/b371fea6e263b5aa4cc81941af4f185d3499890f727b6934d22a10bb0a59949e-04-97b0f232574324adf08c63e0df5ab41164207dcff3ee5f93951eb1abc438cb8f-image.png" />

3. In the **New Quota Request** panel, enter your desired quota in the **New limit** field.  Click **Submit**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/fa55b425236e87ce84368bcf2c53142f045c7a820f82b22b22f7c0601762b770-06-3208d8add8859d1db608a7ee53e9e49d5f8f37ebaf5529483b72fd23b4f72e43-image.png" />

# Create a Virtual Network

If you already have an existing virtual network into which you want to deploy your MongoDB Voyage Azure managed application, skip this section.

1. Click **Create a resource**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/c41769f19d1d48aed5123c30ac1ba553375d0afffcafd7f555aa78df12401464-07-65a1a4137855fb754c1fb715b9572a01a890af895fe845b1cf280c7dc6fa43f4-image.png" />

2. Search for “virtual network”.  Select **Virtual network** from the results.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/268da57e6560c032fb19edde4d2c4956fcc51b6fc62b7ad906ef6f14650ea59a-08-ce17fb57d92bb75fd1daefeb755ab7a2ed85ba0665ad2e890483c629812a4522-image.png" />

3. Click **Create**.

   <Image align="center" border={true} width="600px" src="https://files.readme.io/2cc558bf4f65305e591b551ceccec74de3f722e19ee2e346620f6f25976a5d32-09-827176ae570255127d420b5c2ab577c9f73c71279a9c40dcaedbb8fd6f53a74e-image.png" className="border" />

<br />

4. Fill out the fields in the **Basics** tab.

| **Field**                | **Value**                                                                                |
| :----------------------- | :--------------------------------------------------------------------------------------- |
| **Subscription**         | Select your subscription.                                                                |
| **Resource group**       | Select an existing resource group or create a new resource group.                        |
| **Virtual network name** | Provide a name for your virtual network.                                                 |
| **Region**               | Select your desired region. This region must have the [required resource quota](#quota). |

5. There are several advanced configurations like security, IP addresses, and tags. If you have advanced configuration requirements, enter them in the appropriate tabs. Voyage does not require any advanced configuration to deploy our application. If you do not need any advanced configuration or do not know, click **Review + create** to directly review and create your application.

6. In the **Review + create** tab, review your configuration and click **Create** to confirm. Otherwise, click on the **Previous** button or the corresponding tabs to make changes.

<Image align="center" border={false} width="600px" src="https://files.readme.io/b79d79ecb5516542e46fb9291ad18e7b9eb575ea36e34e7800c40df8b8d61cef-10-e9656a6d141c20fcb548f2e8c2470321b21250f39490c71ae16702726a9cee0d-image.png" />

7. Verify your virtual network creation. As it is being created, you will see the status as "Deployment is in progress."

<Image align="center" border={false} width="600px" src="https://files.readme.io/e9d5f4ab4143803372f0bf94c8dd7ae1f3b8beb549bbdd0b0562e725507e3501-11-1cacbda6382614b186eddac8ee524cae208257edf1cf342d420582a7f0b9bf44-image.png" />

You will see the status change to "Your deployment is complete" when your virtual network has been successfully created.

<Image align="center" border={false} width="600px" src="https://files.readme.io/9954c1014212da3db1cd47a4484ab2fbaeb50cecc660cff2fe0405557388d348-12-8fbbe50dc6ef0651e23c68fe780c408ff015bd4f8724183e48092716aaa233bc-image.png" />

# Deploy a MongoDB Voyage API Endpoint in Virtual Network

In this section, you deploy a MongoDB Voyage Azure managed application in your virtual network.

1. Select the MongoDB Voyage Azure managed application you would like to subscribe to in the <a href="https://azuremarketplace.microsoft.com/en-us/marketplace/apps?page=1&search=mongodb%2C%20inc.%20voyage" target="_blank">Azure Marketplace</a>.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/eb3cd64fbe678fd9e55752898b84f6dd249ca0db37cee1546fad427e3abf6d92-1-azure-marketplace.png" />

2. Click **Get it Now**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/2005e76e174b3979d755fdea8da465a11412ee3f3666822fa8c76b6d4b296ed7-2-azure-get-model.png" />

3. Click **Continue** in the **Create this app in Azure** dialog box.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/fd28ad7b81b7f7631fcec220d220190ae133fb5eac4495ef5d1dcbcbcf7f878d-3-azure-continue.png" />

4. Create a Standard Plan Azure managed application by selecting your subscription and "Standard Plan" from the drop-down menus and clicking **Create**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/0309a4a081fa8068ecd56ee7f90b97658571f96596aec08543f9821c8a78444d-4-azure-create.png" />

5. Fill out the fields in the **Basics** tab. Click **Next** to move to **Network Settings**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/5bc8a52a5c472774b9454e4f3dfb250204ae19f1aa34ef7f176969aa3fe6adb2-5-azure-basics.png" />

| **Field**                  | **Value**                                                                                |
| :------------------------- | :--------------------------------------------------------------------------------------- |
| **Subscription**           | Select your subscription.                                                                |
| **Resource group**         | Select the resource group that contains your desired virtual network.                    |
| **Region**                 | Select your desired region. This region must have the required resource [quota](#quota). |
| **Application Name**       | Provide a name for your application.                                                     |
| **Managed Resource Group** | Provide a name for your managed resource group.                                          |

6. Fill out the fields in the **Network Settings** tab. Once complete, click **Next**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/725d29fe09cd3c327cffcfa30fad0e3e21fe9c5fd3f41f20704dcf5390b4c3db-6-azure-network-settings.png" />

| **Field**                                                         | **Value**                                                                                                                                                                                                             |
| :---------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Select an existing virtual network (do not create a new vnet)** | Select your desired existing virtual network.  The MongoDB Voyage API endpoint will be deployed into this virtual network.                                                                                            |
| **Select or create a subnet that allows HTTP traffic**            | Select your desired subnet.  Select "default" if you do not have custom or advanced subnets within your virtual network.  The deployed MongoDB Voyage API endpoint will have a private IP address within this subnet. |

7. In the **Review + create** tab, review your configuration and click **Create** to confirm. Otherwise, click on the **Previous** button or the corresponding tabs to make changes.

8. Verify your MongoDB Voyage API endpoint creation. As it is being created, you will see the status as "Deployment is in progress."

   <Image align="center" border={false} width="600px" src="https://files.readme.io/aaa3210106e124bdbbb4586bdf004ceed2959beea343c2e5aa5f526457cc3917-7-azure-in-progress.png" />

9. You will see the status change to "Your deployment is complete" when your MongoDB Voyage API endpoint has been successfully created.

<Image align="center" border={false} width="600px" src="https://files.readme.io/0459f36291a2cb8069b2a79afb5a59b6beeef91938f15e2065bacddbf2bd0904-8-azure-deployment-complete.png" />

**IMPORTANT**: Click **Go to resource** to view the application properties.

10. **IMPORTANT**: From the application resource page, get the private IP of the endpoint by clicking on **Parameters and Outputs** under the **Settings** section. Take note of the private IP (”privateIPAddress” output); you will need this IP address to invoke the application endpoints.

<Image align="center" border={false} width="600px" src="https://files.readme.io/7312635235e453b86b34d1ab6495cdfcc3df7e574252d7bc7aba9422e1b1773b-9-azure-ip-address.png" />

If you need help deploying a MongoDB Voyage API endpoint from the Azure Marketplace, contact [MongoDB support](https://www.mongodb.com/services/support).

# Accessing MongoDB Voyage API Endpoints

Once deployed, the MongoDB Voyage API endpoints can be accessed via HTTP requests by any service within the same virtual network.

## Create Bastion Virtual Machine

To demonstrate how to access the MongoDB Voyage API endpoints, we will create a bastion virtual machine within the same virtual network. If you'd like to use or have other existing machines/servers in the network to query the model endpoints, you can skip this section and jump to the [Invoke Voyage API Endpoint](#invoke-voyage-api-endpoint) section.

1. From the Azure portal home, click **Create a resource**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/f8d0fa1e9287a016143308dc7ee48e45c0b8d43e0d9598572066a288e9be955b-24-19f56d7ce7a991a93ad62a0b4dc6a80fecbf796985fbd573ded38c0b83aae103-image.png" />

2. Search for “virtual machine”.  Select **Virtual machine** from the results.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/bf693f97df9e00ccda37c94af24be295e6f27cbe6aa261ea0d3c15d1cb083c6a-25-37b32d246ddc359d64575d026a03c40eb406ea918d203928c69ddb24963023c9-image.png" />

3. Click **Create**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/02974d104f31157473991d20aad181d62693322fd86309198e977c251773d272-26-e69f3d70639926612f9a66a5ab633eadb43da27eb66bf293aae41379ae70e72f-image.png" />

This procedure walks you through a low-cost virtual machine configuration for demo purposes only. If you’re an advanced user, you can make customized configurations.

### Basics

Fill out the fields in the **Basics** tab. Once complete, click **Next**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/17f67cf56fccadd607b97b498107d6c1b29bba2b6ffa03d116cdcb4924fcb693-27-4828fa782ceefde617eec94197b4f8c721e3261ad88ddea12e5a80e555eb7c29-image.png" />

| **Field**                        | **Value**                                                         |
| :------------------------------- | :---------------------------------------------------------------- |
| **Subscription**                 | Select your subscription.                                         |
| **Resource group**               | Select the resource group that contains your Voyage API endpoint. |
| **Virtual machine name**         | Provide a name for your virtual machine.                          |
| **Region**                       | Select the region of your Voyage API endpoint.                    |
| **Availability options**         | Select “No infrastructure redundancy required”                    |
| **Security type**                | Select “Standard”.                                                |
| **Image**                        | Select “Ubuntu Server 24.04 LTS - x64 Gen2”.                      |
| **VM architecture**              | Select “x64”.                                                     |
| **Run with Azure Spot discount** | Leave box unchecked.                                              |
| **Size**                         | Select “Standard\_B1s - 1 vcpu, 1GiB memory”.                     |
| **Enable Hibernation**           | Leave box unchecked.                                              |
| **Authentication type**          | Select “SSH public key”.                                          |
| **Username**                     | Enter “voyage”.                                                   |
| **SSH public key source**        | Select “Generate new key pair”.                                   |
| **SSH Key Type**                 | Select “RSA SSH Format”.                                          |
| **Key pair name**                | Enter “vm-voyage\_key”.                                           |
| **Public inbound ports**         | Select “Allow selected ports”.                                    |
| **Select inbound ports**         | Select “SSH (22)”.                                                |

### Disks

Fill out the fields in the **Disks** tab. Once complete, click **Next** to move to **Networking**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/146842d7a029274fd29e983a11a027d02c895d097c7dc089ae3e687eae0aec33-29-ac559c4050f1a8404ead35276f76670e480de5c8f08c22810a652d42a5264b6e-image.png" />

| **Field**                           | **Value**                                          |
| :---------------------------------- | :------------------------------------------------- |
| **Encryption at host**              | Leave box unchecked.                               |
| **OS disk size**                    | Select “Image default (30 GiB)”.                   |
| **OS disk type**                    | Select “Standard HDD (locally-redundant storage)”. |
| **Delete with VM**                  | Check the box.                                     |
| **Key management**                  | Select “Platform-managed key”.                     |
| **Enable Ultra Disk compatibility** | Leave box unchecked.                               |

### Networking

Fill out the fields in the **Networking** tab. Once complete, click **Review + create**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/146842d7a029274fd29e983a11a027d02c895d097c7dc089ae3e687eae0aec33-29-ac559c4050f1a8404ead35276f76670e480de5c8f08c22810a652d42a5264b6e-image.png" />

| **Field**                                   | **Value**                                                                                                                                               |
| :------------------------------------------ | :------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Virtual network                             | **IMPORTANT**. Select the virtual network in which your Voyage API endpoint is deployed.                                                                |
| Subnet                                      | **IMPORTANT**. Select the subnet within the virtual network in which your Voyage API endpoint is deployed.                                              |
| Public IP                                   | **IMPORTANT**. Create a new public IP. If you do not create this, you will not be able to access your virtual machine from outside the virtual network. |
| NIC network security group                  | Select “Basic”.                                                                                                                                         |
| Public inbound ports                        | Select “Allow selected port”.                                                                                                                           |
| Select inbound ports                        | Select “SSH (22)”.                                                                                                                                      |
| Delete public IP and NIC when VM is deleted | Leave box unchecked.                                                                                                                                    |
| Enable accelerated networking               | Leave box unchecked.                                                                                                                                    |
| Load balancing options                      | Select “None”.                                                                                                                                          |

### Review and Create

1. In the **Review + create** tab, review your configuration and click **Create** to confirm. Otherwise, click on the **Previous** button or the corresponding tabs to make changes.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/4c5c6e2e636b9c615612db61d220bda3413d08baed9f9e966b911cb55cba6c4a-32-c0d0b5f3efc8abe1793eb87eae0117e6cd25489ba4f8761adf912b97834fa951-image.png" />

2. A new **Generate new key pair** modal appears. Click **Download private key and create resource** to save the key to your local machine.  Note where you saved the key.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/4c5c6e2e636b9c615612db61d220bda3413d08baed9f9e966b911cb55cba6c4a-32-c0d0b5f3efc8abe1793eb87eae0117e6cd25489ba4f8761adf912b97834fa951-image.png" />

3. Verify your bastion virtual machine creation. As it is being created, you will see the status as "Deployment is in progress." You will see the status change to "Your deployment is complete" when your bastion virtual machine has been successfully created.  Click **Go to resource** to get your bastion virtual machine public IP address.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/4c5c6e2e636b9c615612db61d220bda3413d08baed9f9e966b911cb55cba6c4a-32-c0d0b5f3efc8abe1793eb87eae0117e6cd25489ba4f8761adf912b97834fa951-image.png" />

   <br />

4. In your bastion virtual machine page, you can find the public IP address in the **Overview** section, under **Essentials**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/1afdff8a906e187859aa9c1475b99897aaa232afb99f80a46a3fab773674d1ff-33-b29341b4397dac410b0f387f7788258b881f05513bfc377f89cc4c977bbcbf2e-image.png" />

   <br />

5. Update the permissions of the SSH private key you downloaded to read-only:
   `chmod 400 vm-voyage_key.pem`

6. Securely login into the bastion virtual machine shell (SSH) using your private key.  The format is: `ssh -i {private-ssh-key} voyage@{bastion-vm-public-ip-address}`.  For example: `ssh -i vm-voyage_key.pem voyage@52.143.109.43`.

## Invoke MongoDB Voyage API Endpoint

1. Verify the MongoDB Voyage API is reachable with the following endpoint:

`http://{voyage-app-vnet-private-ip}/info`. For example, using cURL: `curl -X GET http://10.0.0.4/info`.

2. You can make a request to the Voyage API with the following endpoint: `http://{voyage-app-vnet-private-ip}/embeddings`.  For example, using cURL:

```curl
curl -X GET "http://10.0.0.4/embeddings" -H "Content-Type: application/json" -d '{ "input": ["Best-in-class embedding models and rerankers"], "input_type": "query" }'
```

An example response:

```curl
{"model":"voyage-4","model_loaded":true,"tokenizer_initialized":true,"loading_status":"completed","gpu_info":{"count":1,"memory_allocated_mb":XXX,"memory_reserved_mb": XXX}}
```

For all the endpoint parameters, refer to the  <a href="https://docs.voyageai.com/reference/" target="_blank">API reference</a>.

# Delete a MongoDB Voyage API Application

To delete your MongoDB Voyage API endpoint, go to your application and click the **Delete** button in the **Overview** section. In the dialog box that appears, click **Yes** to confirm the deletion. This also deletes the associated managed resource group.

## Delete Bastion Virtual Machine

If you have provisioned a bastion virtual machine, delete the virtual machine to avoid incurring wasteful costs and unexpected charges.

1. Go to your bastion virtual machine and click the **Delete** button in the **Overview** section. A delete panel appears.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/4b6ff53f2c36a1251569f2148bca43121d452f6d89ebb1d23f51aebd9e7c0a6e-35-42681d59da66b617a69d19b255d70a8e922e2a907000142a58c4c12dc4f95529-image.png" />

2. In the delete panel, ensure all the virtual machine resources are deleted by checking all the checkboxes shown in the screenshot below: **Apply force delete**, **OS disk**, **Network interfaces**, **Public IP addresses**.  Check the acknowledgement checkbox: "I have read and understand that this virtual machine as well as any selected associated resources listed above will be deleted." Finally, click **Delete**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/04ef6f6c62e538788990c6bd383007e8a2a6846fad249f9e043c8728899295e6-36-4b73f5a126dbffdf5315f55e4508101bd8723fac6921a3b54e6c437b1d2fc783-image.png" />