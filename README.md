# CloudGuard CSPM AWS Continuous Onboarding
This project is intended to be used to continuously onboard an AWS Public Cloud Account in CloudGuard CSPM.     
You can find the CloudFormation Template JSON files in this folder and the direct link to launch them in your system.     
The IAM Role created are based on my latest CloudFormation Templates [gbrembati / cloudguard-cspm-aws](https://github.com/gbrembati/cloudguard-cspm-aws) and the lambda code is based from the public Check Point Onboarding Scripts [dome9 / onboarding-scripts](https://github.com/dome9/onboarding-scripts)
 
## How to start?
At first, you will need to have a CloudGuard CSPM account; if you don't have it, you can create one with these links:
1. Create an account in [Europe Region](https://secure.eu1.dome9.com/v2/register/invite)
2. Create an account in [United States Region](https://secure.dome9.com/v2/register/invite)

## Prerequisite
You will need to get the API credentials that you will be using by the Lambda Function to onboard the accounts.
![CSPM Service Account](/zimages/create-cpsm-serviceaccount.jpg)
       
Remember to copy these two values! You will need to enter them in the Stack Parameters later.

## How to launch the template
Either copy the JSON file and then uploaded it to a newly created stack or launch the CloudFormation directly.
**Use this link** to Launch the CloudFormation in your AWS root account: [Launch Stack](https://eu-west-1.console.aws.amazon.com/cloudformation/home#/stacks/create/review?stackName=cft-cloudguard-continuous-onboarding&templateURL=https://cspm-onboarding.s3.eu-west-1.amazonaws.com/continous-onboarding-stack.yaml)

## How to use the Template
Please insert all the needed parameters to the Stack:
1. **CloudGuardAPIID**: The CloudGuard Service Access ID to use
2. **CloudGuardAPISecret**: The CloudGuard Service Access Key to use
3. **CloudGuardMode**: CloudGuard mode to onboard your AWS accounts as
4. **CloudGuardRegion**: Where does your CloudGuard Tenant reside?
5. **LambdaRate**: The frequency that determines when CloudWatch Events runs the rule that triggers the Lambda function
6. **OrganizationRole**: The IAM Role name to assume in each child account

## Architecture Created
As per this CloudFormation stack the following architecture is then created:     
![AWS Architecture](/zimages/schema-serverless-arch.jpg)
