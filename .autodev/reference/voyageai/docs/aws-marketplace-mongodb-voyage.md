> ## Documentation Index
> Fetch the complete documentation index at: https://docs.voyageai.com/llms.txt
> Use this file to discover all available pages before exploring further.

# MongoDB Voyage AI Models in AWS

Deploy MongoDB Voyage AI models using AWS Marketplace

AWS Marketplace <a href="https://aws.amazon.com/marketplace/seller-profile?id=c9032c7b-70dd-459f-834f-c1e23cf3d092" target="_blank">model packages</a> are containerized solutions that include the model and inference code. You deploy them in your account and virtual private cloud (VPC). Model packages have the following key benefits:

1. **Data flow and access control**: Deploy models in your account and VPC to maintain full control over data flow and API access. This addresses data privacy risks associated with third-party or multi-tenant serving.
2. **Reliability and compliance backed by AWS**: AWS serves as your sub-processor, so you inherit all AWS reliability and compliance guarantees.
3. **Billing and payment through AWS**: Use your existing AWS billing information and credits to purchase MongoDB Voyage AI models through marketplace listings. You don't need to manage a separate third-party payment and billing system.

You can deploy a model package as a [real-time inference API endpoint](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints.html) or a [batch transform job](https://docs.aws.amazon.com/sagemaker/latest/dg/batch-transform.html). Real-time inference API endpoints provide persistent, fully managed API endpoints for request-by-request inference. Batch transform jobs run finite execution processes for bulk inference on datasets, writing predictions to a file. Both deployment types run on AWS instances, such as GPUs.

# Available Models

To see which models are available on AWS Marketplace, go to the [MongoDB Marketplace Seller Profile](https://aws.amazon.com/marketplace/seller-profile?id=c9032c7b-70dd-459f-834f-c1e23cf3d092).

# Pricing

Pricing for the use of a MongoDB Voyage AI model package consists of software pricing and infrastructure pricing, both at an hourly rate. Software pricing covers the cost of model usage, while your total hourly cost is the sum of the software pricing and the infrastructure pricing. Pricing rates vary based on deployment type (real-time inference API endpoint versus batch transform job), instance type, and region. All MongoDB Voyage models come with a free trial. You can find the pricing details for each model package on the product listing page in the AWS Marketplace.

The following sections demonstrate how to subscribe and deploy the models.

# Prerequisites

You must have the following AWS identity access management (IAM) permissions to subscribe to AWS Marketplace listings.

* [AmazonSageMakerFullAccess](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonSageMakerFullAccess.html) (AWS Managed Policy)
* aws-marketplace:ViewSubscriptions
* aws-marketplace:Subscribe
* aws-marketplace:Unsubscribe

To add them, [sign into your AWS account console](https://console.aws.amazon.com/iam/) and review the [AWS documentation](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_manage-attach-detach.html#add-policies-console) for instructions.

# Procedure

To subscribe by using the AWS Marketplace:

1. Select the MongoDB Voyage AI model package to subscribe to in the [AWS Marketplace](https://aws.amazon.com/marketplace/seller-profile?id=c9032c7b-70dd-459f-834f-c1e23cf3d092).

2. Click **Continue to Subscribe**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/ce4cb30bc98c37a67518f2245d64c0c773a51a1c15eb6a76d1c8fe3f64fe92c9-1-aws-subscribe.png" />

<br />

3. Click **Accept Offer**.

<Image align="center" border={false} width="600px" src="https://files.readme.io/6ca86c1275221615b7aa4eae2fd9ca42d23230b4fb837c8c43d4cec474744e6f-2-aws-accept-offer.png" />

4. Confirm you have successfully subscribed and close the window.

<Image align="center" border={false} width="600px" src="https://files.readme.io/296037765978980ab38a37f8bae2f2aa54a9024e371d6ead299eaf32a7fe9619-3-aws-confirmation.png" />

You can also confirm and manage your AWS Marketplace subscriptions through the console’s [manage subscription page](https://aws.amazon.com/marketplace/library/ref=gtw_navgno_library). You can [cancel your subscription](https://docs.aws.amazon.com/marketplace/latest/buyerguide/cancel-machine-learning-subscription.html) at any time, but note that canceling your subscription [***does not***](https://docs.aws.amazon.com/marketplace/latest/buyerguide/cancel-machine-learning-subscription.html) terminate your existing real-time inference endpoints or batch transform jobs. To learn more, see [Delete Real-Time Inference Endpoints](#delete-real-time-inference-endpoints).

Model package deployment requires specific SageMaker instances (e.g., ml.g5.xlarge). The exact quota names for these instances end with “endpoint usage” and “transform job usage” (e.g., “ml.g5.2xlarge for endpoint usage”, and “ml.g5.2xlarge for transform job usage”). These [quotas](https://docs.aws.amazon.com/general/latest/gr/sagemaker.html#limits_sagemaker) are typically set to zero by default. To [request quota increases](https://docs.aws.amazon.com/servicequotas/latest/userguide/request-quota-increase.html) if needed, go to the [SageMaker Service Quotas console](https://console.aws.amazon.com/servicequotas/home/services/sagemaker/quotas).

If you need help subscribing and deploying a MongoDB Voyage AI model package from the AWS Marketplace,
contact [MongoDB support](https://www.mongodb.com/services/support).

# Model Package Deployment

This section includes guidance on how to deploy a model package using Amazon SageMaker Studio and Jupyter Notebooks.

## Amazon SageMaker Studio

[Amazon SageMaker Studio](https://aws.amazon.com/sagemaker/studio/) is a web-based interface for ML and AI development that includes a hosted notebook environment already authenticated to your AWS account. You can skip this section if you have another preferred Jupyter notebook execution environment, such as your local machine, where you can authenticate to your AWS account from the environment. Follow the SageMaker documentation to [launch SageMaker Studio](https://docs.aws.amazon.com/sagemaker/latest/dg/studio-updated-launch.html), and then [launch a JupyterLab environment](https://docs.aws.amazon.com/sagemaker/latest/dg/studio-updated-jl-user-guide.html).

<Image alt="Amazon SageMaker Studio" border={false} src="https://files.readme.io/97ce1bf372af3f435910e8c98c38405d61ddf7fffa37c98eee82fd522c581fd0-image.png" />

## Jupyter Notebook

You can use the [example Jupyter notebook](https://github.com/voyage-ai/voyageai-aws/blob/main/deploy_mongodb_voyage_model_package_sagemaker.ipynb) to get started with Python by using the AWS SDK ([Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html)) and the [Amazon SageMaker Python SDK](https://sagemaker.readthedocs.io/en/stable/). You can run the notebook in SageMaker Studio or your preferred Jupyter notebook execution environment after cloning the [Voyage AI AWS repo](https://github.com/voyage-ai/voyageai-aws/tree/main). For example, by running `git clone https://github.com/voyage-ai/voyageai-aws.git`.

<Image alt="JupyterLab git clone" border={false} src="https://files.readme.io/f7669bb78111a58f7dca9326090a48332eb2a33676b1521e00ed043447515d36-image.png" />

Alternatively, you can directly download the notebook from GitHub and upload it to SageMaker Studio or your preferred notebook environment.

Once the notebook is in SageMaker Studio or your preferred execution environment, you can run the provided code to deploy the models.

## Delete Real-Time Inference Endpoints

Do not run real-time inference endpoints longer than necessary. If you do, they might incur wasteful costs and lead to unexpected charges. If you're using the provided Jupyter notebook, ensure that you run the **Clean Up** code, which deletes the endpoint and associated endpoint configuration. You can manage and delete endpoints through SageMaker Studio or the SageMaker console. To learn more, see [AWS documentation](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints-manage.html).

# Advanced Deployment

The Jupyter notebook described in the previous section is meant to get you started and help you learn how to deploy model packages. However, there are several other ways to deploy model packages, such as CloudFormation, the SageMaker Console, and the AWS CLI. These alternative methods might be better suited for your existing production workflows. For example:

* CloudFormation for declarative infrastructure specification
* SageMaker Console for interactive UI-based deployment
* AWS CLI for programmatic shell orchestration

To configure and deploy a model package using these methods:

1. Go to the product listing page for the subscribed MongoDB Voyage model from the [AWS Marketplace](https://aws.amazon.com/marketplace/seller-profile?id=c9032c7b-70dd-459f-834f-c1e23cf3d092).
2. Click on **Continue to Subscribe** in the upper-right corner.

<Image align="center" border={false} width="600px" src="https://files.readme.io/3fea0bfdcb8bae9ad30b03ce37f245442a326002be00d5e28ff7db0e1a40418d-1-aws-subscribe.png" />

3. In the **Subscribe to this software** page, you should see that you are **Already Subscribed**. Click on the **Continue to configuration** button.

<Image align="center" border={false} width="600px" src="https://files.readme.io/bff1c1f2f0200979f234de9cd09152b5e4a8fa4b93ce4bb43aa593220e09251d-4-aws-continue-to-configuration.png" />

4. In the **Configure and launch** page, you can select your desired launch method. The configuration settings update according to the corresponding instructions and resources for the selected method.

<Image align="center" border={false} width="600px" src="https://files.readme.io/3c64daed2af342ca3ef40aab66e7981a0fd8cf8a7d1d91b40cabc110327cb8de-5-aws-configuration.png" />