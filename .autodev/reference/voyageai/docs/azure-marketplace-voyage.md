> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# Voyage AI Models in Azure

Deploy Voyage AI models using Azure Marketplace

<Callout icon="🚧">
  Models published under Voyage AI are no longer updated and will be removed in the future. For the latest models and all future updates, use the official MongoDB listing. To learn more, see [MongoDB Voyage AI Models in Azure](azure-marketplace-mongodb-voyage).
</Callout>

Voyage Azure managed applications are Voyage models deployed as real-time inference API endpoints in a customer Azure account and virtual network (VNet). Azure managed applications offer several benefits to customers:

1. **Data flow and access control**. Data never leave the customers' virtual network, comprehensively addressing data privacy risks associated with third-party or multi-tenant serving.
2. **Reliability and compliance backed by Azure**. Only Azure will be the customer's sub-processor, and customers will inherit all Azure's reliability and compliance guarantees.
3. **Billing and payment through Azure**. By transacting through a marketplace listing, customers can utilize their existing Azure billing information and credits to procure Voyage models. This streamlined process eliminates the need to manage a separate third-party payment and billing system.

**Pricing.** Voyage Azure managed applications are billed hourly. The total hourly cost will be the sum of the virtual machine (VM) price ($5 per hour) and the price of the underlying instance in your region.  There is no management cost for this managed Azure application; this is why the listed Azure managed application monthly price is $0.

# Prerequisites

1. **Azure Subscription**. Ensure you have an existing <a href="https://learn.microsoft.com/en-us/microsoft-365/enterprise/subscriptions-licenses-accounts-and-tenants-for-microsoft-cloud-offerings?view=o365-worldwide#subscriptions" target="_blank">Azure subscription</a>.
2. **Virtual Network.** You must have an existing virtual network into which you will deploy a Voyage Azure managed application. If do not have an existing one and need help creating one, see the **[Create a Virtual Network](#create-a-virtual-network)** section below.
3. **Quota in Subscription and Region**. You must have 24 Standard NCADS\_A100\_v4 Family vCPUs quota for each Voyage Azure managed application you want to deploy.  The quota is specific to an Azure subscription and region. If you need help checking your quota or requesting a quota increase, see the **[Quota](#quota)** section below.

If you already meet all the prerequisites, you can jump to the **[Create a Voyage API Endpoint in Virtual Network](#create-a-voyage-api-endpoint-in-virtual-network)** section below.

# Quota

In this section, we walk through how to check your quota and request an increase if necessary.  You can skip this section if you know you have sufficient quota.

## Check Quota

1. Go to **Subscriptions** in your <a href="https://portal.azure.com/" target="_blank">Azure portal</a>.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/526af4ac1a7d0826f5cd09bc7048bfbc61f4eb620a38d401335443d7572a2145-01-ba0d965becdd40c4a2fbadce985619ccf474a167b02bc437030a418b81a1c875-image.png" />

2. Select the subscription you want to use for the Azure managed application.  In the example below, we selected our "Pay-As-You-Go" subscription.  Within your subscription page, select **Usage + quotas** under **Settings**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/9204ea20c76ff1eb90d841a1fe24f8809e1c501ed5f276ae25b712da9a5402f8-02-c8828e1c9de19b41032c0241af2c3bebd4647b3d9a50f50bd74012d4ff8e7898-image.png" />

3. Enter "Standard NCADS\_A100\_v4 Family vCPUs" in the search bar.  Filter the **Region** for your desired region; in the example below, we filtered the region for "West US 2."

   <Image align="center" border={false} width="600px" src="https://files.readme.io/968d1040ec7ccf9e183a1a14c7bc74ae17b633639d6badcac3f7029d3968692e-03-b8bb479d5a5f79db160259792e642afd7cb1be0870bb849900fee5bfcd1e1a64-image.png" />

4. Ensure you have sufficient "Standard NCADSA100\_v4 Family vCPUs" quota for the number of Voyage Azure managed applications you want to deploy.  Each Voyage Azure managed application requires  ***24 Standard NCADS\_A100\_v4 Family vCPUs***.  If you do not have sufficient quota, continue to the next section (**[Request Quota Increase](#request-quota-increase)**) to request more quota.

## Request Quota Increase

From the **Usage + quotas** page of your desired subscription, you can request to increase your quota:

1. Check the checkbox for the “Standard NCADS\_A100\_v4 Family vCPUs” quota.  Select the **New Quota Request** drop down, and select **Enter a new limit**.  A **New Quota Request** panel will appear.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/b371fea6e263b5aa4cc81941af4f185d3499890f727b6934d22a10bb0a59949e-04-97b0f232574324adf08c63e0df5ab41164207dcff3ee5f93951eb1abc438cb8f-image.png" />
2. In the **New Quota Request** panel, enter your desired quota in the **New limit** field.  Click **Submit**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/c4de97511cd0881a1ab658b4dd9fa38733e13f918dc1a0feab993881fa1f3c93-05-94f263575a45b4865cff4e413e8ae5af631d8a67f8cb2f8e31869aacfa0d906d-image.png" />

# Create a Virtual Network

You can skip this step if you already have an existing virtual network into which you want to deploy your Voyage Azure managed application.

1. Click **Create a resource**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/fa55b425236e87ce84368bcf2c53142f045c7a820f82b22b22f7c0601762b770-06-3208d8add8859d1db608a7ee53e9e49d5f8f37ebaf5529483b72fd23b4f72e43-image.png" />
2. Search for “virtual network”.  Select **Virtual network** from the results.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/c41769f19d1d48aed5123c30ac1ba553375d0afffcafd7f555aa78df12401464-07-65a1a4137855fb754c1fb715b9572a01a890af895fe845b1cf280c7dc6fa43f4-image.png" />
3. Click **Create**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/268da57e6560c032fb19edde4d2c4956fcc51b6fc62b7ad906ef6f14650ea59a-08-ce17fb57d92bb75fd1daefeb755ab7a2ed85ba0665ad2e890483c629812a4522-image.png" />

   <br />
4. Fill out the fields in the **Basics** tab.

   <Image align="center" border={true} width="600px" src="https://files.readme.io/2cc558bf4f65305e591b551ceccec74de3f722e19ee2e346620f6f25976a5d32-09-827176ae570255127d420b5c2ab577c9f73c71279a9c40dcaedbb8fd6f53a74e-image.png" className="border" />

   | **Field**                | **Value**                                                                                                                                                         |
   | :----------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | **Subscription**         | Select your subscription.                                                                                                                                         |
   | **Resource group**       | Select an existing resource group or create a new resource group.                                                                                                 |
   | **Virtual network name** | Provide a name for your virtual network.                                                                                                                          |
   | **Region**               | Select your desired region.  We assume your desired region has the required resource quota (see [Quota in Subscription and Region](#prerequisites) prerequisite). |
5. There are several advanced configurations like security, IP addresses, and tags. If you have advanced configuration requirements, feel free to enter them in the appropriate tabs. Voyage does not require any advanced configuration to deploy our application. If you do not need any advanced configuration or do not know, click **Review + create** to directly review and create your application.
6. In the **Review + create** tab, review your configuration and if it looks good, click **Create**. Otherwise, go to previous tabs to make changes; you can click on the **Previous** button at the bottom or directly click on the tab of interest.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/b79d79ecb5516542e46fb9291ad18e7b9eb575ea36e34e7800c40df8b8d61cef-10-e9656a6d141c20fcb548f2e8c2470321b21250f39490c71ae16702726a9cee0d-image.png" />
7. Verify your virtual network creation. As it is being created, you will see the status as "Deployment is in progress."

   <Image align="center" border={false} width="600px" src="https://files.readme.io/e9d5f4ab4143803372f0bf94c8dd7ae1f3b8beb549bbdd0b0562e725507e3501-11-1cacbda6382614b186eddac8ee524cae208257edf1cf342d420582a7f0b9bf44-image.png" />

   You will see the status change to "Your deployment is complete" when your virtual network has been successfully created.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/9954c1014212da3db1cd47a4484ab2fbaeb50cecc660cff2fe0405557388d348-12-8fbbe50dc6ef0651e23c68fe780c408ff015bd4f8724183e48092716aaa233bc-image.png" />

# Create a Voyage API Endpoint in Virtual Network

We will deploy a Voyage Azure managed application to create a Voyage API endpoint in your virtual network.

1. Select the Voyage Azure managed application you would like to subscribe to in the <a href="https://azuremarketplace.microsoft.com/en-us/marketplace/apps?search=voyageaiinnovationsinc1718340344903" target="_blank">Azure Marketplace</a>.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/97d9063eaba59b64a99909cc6d1e0188900af38e517755f12924335c38bbc1f5-13-193c48353f338928fddb8dbbf5f691ac7fff90590e1e7022adf00d154dd3aeeb-image.png" />

2. Click **Get it Now**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/f9a65d3312566ab470625d4d9d98103828ea8a4f6e499dcdd303646c6e1c2642-14-dc4eb276003c8d899a83e0b495aef7f31d1120971567b247e36f884c11a52925-image.png" />

3. Click **Continue** in the **Create this app in Azure** modal.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/17040734609878099df55e28fd9c509c112c86bd20b2b2362cc6877d502c8398-15-687ebd870be081be72036e335e929a949d186fa6b45ccae4159890eee1aa19ed-image.png" />

4. Create a Standard Plan Azure managed application by selecting "Standard Plan" and clicking **Create**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/5095a0db7b89f93a482331a61a2f92f33588c47a06b99291e23f81d1c5877452-16-57c69f8431d9b5b7ae57b83f7c3ba794b87a67f8fd7e25cf653ba95d41c511b1-image.png" />

5. Fill out the fields in the **Basics** tab. Click **Next** to move to **Network Settings**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/84ed094d47fe2b6b58f89a07d91439b0003a9758e082e6be508d6e6f5fd7a2ec-17-f19b6b1dd0f5858d89f5c0ed7ca32362e1b39bfd33844e23fa266c183301c978-image.png" />

   | **Field**            | **Value**                                                                                                                                                          |
   | :------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
   | **Subscription**     | Select your subscription.                                                                                                                                          |
   | **Resource group**   | Select the resource group that contains your desired virtual network.                                                                                              |
   | **Region**           | Select your desired region.  We assume your desired region has the required resource quota (see [Quota in Subscription and Region](#prerequisites)  prerequisite). |
   | **Application Name** | Provide a name for your application.                                                                                                                               |

6. Fill out the fields in the **Network Settings** tab. Once complete, click **Next** to move to **Review + create**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/979a4d22572dd95fb3316e1366033c3fd97154b965bbfed5b8289b9e55b8c6d6-18-9eaf9112dbc1fe6ae7a3a183f98855aa592b34c4026748a2cdb6549a178dcfc8-image.png" />

   | **Field**                                                         | **Value**                                                                                                                                                                                                     |
   | :---------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
   | **Select an existing virtual network (do not create a new vnet)** | Select your desired existing virtual network.  The Voyage API endpoint will be deployed into this virtual network.                                                                                            |
   | **Select or create a subnet that allows HTTP traffic**            | Select your desired subnet.  Select "default" if you do not have custom or advanced subnets within your virtual network.  The deployed Voyage API endpoint will have a private IP address within this subnet. |

7. In the **Review + create** tab, review your configuration and if it looks good, click **Create**. Otherwise, go to previous tabs to make changes; you can click on the **Previous** button at the bottom or directly click on the tab of interest.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/57c81cb2d59dcd55a78d4f13a4eea2dbb4e4408219cb846d3a85768df98ae036-19-33d2c5ac310a829fc88a5049399bb072d5a8d59c2440a64dd0f36993523c3dd0-image.png" />

8. Verify your Voyage API endpoint creation. As it is being created, you will see the status as "Deployment is in progress."

   <Image align="center" border={false} width="600px" src="https://files.readme.io/e2495183969559ddfa0be5be4205fce43d2a8cdaf1e144739b60535242e9a79d-20-4f907d50eb7f06a3b443255ecc6746455cec3973c0f37ec8b0ac99e99758a3b0-image.png" />

   You will see the status change to "Your deployment is complete" when your Voyage API endpoint has been successfully created.

   **IMPORTANT**: Click **Go to resource** to view the application properties.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/a7707576f7154006aec5e1f10a17eeb2d33e2ffc5606f617ab978d902448d554-21-e77db7b63c3778a39b81368025361bd75a9c375c95a24a9b519402a99220e7e5-image.png" />

9. **IMPORTANT**: From the application resource page, get the private IP of the Voyage endpoint by clicking on **Parameters and Outputs** under the **Settings** section.  Take note of the private IP (”privateIPAddress” output); you will need this IP address to invoke the application endpoints.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/ea76b2fad26c5c513b220e5ffc1f8bb373ca94122cd2c30ed19b1905c33dbda0-22-c94089609500c6126b3f83d1fda9e7f75744995aa9fa13cbf43f33f78eb8d99a-image.png" />

   <br />

   <Image align="center" border={false} width="600px" src="https://files.readme.io/35dd0543c3473fd0cdc3193723644791aeaf69134d79176e4b57e7b226d6abfa-23-e2546c18acc5212d72950134e775ec7a76b3011c3ad3e1d099b0ef45e9e76cbd-image.png" />

   <br />

# Accessing Voyage API Endpoints

Once deployed, the Voyage API endpoints can be accessed via HTTP requests by any service within the same virtual network.

## Create Bastion Virtual Machine

To demonstrate how to access the Voyage API endpoints, we will create a bastion virtual machine within the same virtual network. If you’d like to use or have other existing machines/servers in the network to query the model endpoints, you can skip this section and jump to the [Invoke Voyage API Endpoint](#invoke-voyage-api-endpoint) section.

1. From the Azure portal home, click **Create a resource**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/f8d0fa1e9287a016143308dc7ee48e45c0b8d43e0d9598572066a288e9be955b-24-19f56d7ce7a991a93ad62a0b4dc6a80fecbf796985fbd573ded38c0b83aae103-image.png" />
2. Search for “virtual machine”.  Select **Virtual machine** from the results.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/bf693f97df9e00ccda37c94af24be295e6f27cbe6aa261ea0d3c15d1cb083c6a-25-37b32d246ddc359d64575d026a03c40eb406ea918d203928c69ddb24963023c9-image.png" />
3. Click **Create**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/02974d104f31157473991d20aad181d62693322fd86309198e977c251773d272-26-e69f3d70639926612f9a66a5ab633eadb43da27eb66bf293aae41379ae70e72f-image.png" />

We will walk through a low-cost virtual machine configuration for demo purposes only.  Advanced users are welcome to make customized configurations.

### Basics

Fill out the fields in the **Basics** tab. Once complete, click **Next** to move to **Disks**.

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

<Image align="center" border={false} width="600px" src="https://files.readme.io/c5099e85c5e9ee96e6e736a6f2144e88220c94c32118aab56836d9bbc62773bd-28-3589c1ac0df326385f2b0c4caeb76963f297d00d43723333985a2e5dc1fc1c6d-image.png" />

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

1. In the **Review + create** tab, review your configuration and if it looks good, click **Create**. Otherwise, go to previous tabs to make changes; you can click on the **Previous** button at the bottom or directly click on the tab of interest.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/0b90c0c44ff0271102db31c4e37e824030c24306f0182da3c015dc17cf10a297-30-3221f77a902ad4c823b73ff06c1be83ac9661ded41fcb9ae03edd8caaf1f2504-image.png" />

   <br />
2. A new **Generate new key pair** modal will appear. Click **Download private key and create resource** to save the key to your local machine.  Note where you saved the key.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/22aae4743ba74276d69baea03c950dc15669e773a9db3ea715ea7cf552cde02e-31-f1b7922951d2b3b1d206536596ba2e5f2c5cade23d51770f97dabfd576f03535-image.png" />
3. Verify your bastion virtual machine creation. As it is being created, you will see the status as "Deployment is in progress." You will see the status change to "Your deployment is complete" when your bastion virtual machine has been successfully created.  Click **Go to resource** to get your bastion virtual machine public IP address.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/4c5c6e2e636b9c615612db61d220bda3413d08baed9f9e966b911cb55cba6c4a-32-c0d0b5f3efc8abe1793eb87eae0117e6cd25489ba4f8761adf912b97834fa951-image.png" />

   <br />
4. In your bastion virtual machine page, you can find the public IP address in the **Overview** section, under **Essentials**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/1afdff8a906e187859aa9c1475b99897aaa232afb99f80a46a3fab773674d1ff-33-b29341b4397dac410b0f387f7788258b881f05513bfc377f89cc4c977bbcbf2e-image.png" />

   <br />
5. Update the permissions of the SSH private key you downloaded to read-only:
   `chmod 400 vm-voyage_key.pem`
6. Securely login into the bastion virtual machine shell (SSH) using your private key.  The format is: `ssh -i {private-ssh-key} voyage@{bastion-vm-public-ip-address}`.  For example: `ssh -i vm-voyage_key.pem voyage@52.143.109.43`.

## Invoke Voyage API Endpoint

1. Verify Voyage API is reachable with the following endpoint: `http://{voyage-app-vnet-private-ip}/info`. For example, using cURL: `curl -X POST http://10.0.0.4/info`. An example successful response: "Voyage AI model \[voyage-multilingual-2] up and running!"
2. You can make a request to the Voyage API with the following endpoint: `http://{voyage-app-vnet-private-ip}/embeddings`.  For example, using cURL:

```curl
curl -X POST "http://10.0.0.4/embeddings" -H "Content-Type: application/json" -d '{ "input": ["Best-in-class embedding models and rerankers"], "input_type": "query" }'
```

An example response:

```curl
{"data":[{"object":"embedding","embedding":["-0.031104945",...,"-0.037366055"],"index":0}],"object":"list","model":"voyage-multilingual-2","usage":{"total_tokens":13}}
```

For all the endpoint parameters, please see our <a href="https://docs.voyageai.com/reference/" target="_blank">API reference</a>.

# Delete a Voyage API Application

To delete your Voyage API endpoint, go to your application and click the **Delete** button in the **Overview** section.  A confirmation modal will appear; click **Yes** in the modal to confirm the deletion. Note, you do not need to worry about deleting the associated managed resource group; it will be deleted as part of the application deletion.

<Image align="center" border={false} width="600px" src="https://files.readme.io/e47bb5b8e9088f590d8b1b460163b6b360c0a03baf04cebc9f88bc9331af36ba-34-619f7f35bd6e9a1789061c793d19690c6d9eaf3e940a0767a1f774bb079763f7-image.png" />

## Delete Bastion Virtual Machine

If you provisioned a bastion virtual machine, be sure to delete the virtual machine if you no longer need it. It will incur wasteful costs, potentially leading to unexpected charges.

1. Go to your bastion virtual machine and click the **Delete** button in the **Overview** section.  A delete panel will appear.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/4b6ff53f2c36a1251569f2148bca43121d452f6d89ebb1d23f51aebd9e7c0a6e-35-42681d59da66b617a69d19b255d70a8e922e2a907000142a58c4c12dc4f95529-image.png" />
2. In the delete panel, ensure all the virtual machine resources are deleted by checking all the checkboxes shown in the screenshot below: **Apply force delete**, **OS disk**, **Network interfaces**, **Public IP addresses**.  Check the acknowledgment checkbox: "I have read and understand that this virtual machine as well as any selected associated resources listed above will be deleted." Finally, click **Delete**.

   <Image align="center" border={false} width="600px" src="https://files.readme.io/04ef6f6c62e538788990c6bd383007e8a2a6846fad249f9e043c8728899295e6-36-4b73f5a126dbffdf5315f55e4508101bd8723fac6921a3b54e6c437b1d2fc783-image.png" />

If you need assistance subscribing and deploying a Voyage Azure managed application from the Azure Marketplace, please send an email to [contact@voyageai.com](mailto:contact@voyageai.com) or join our <a href="https://discord.gg/zAU7GQEmvT" target="_blank">Discord</a>.