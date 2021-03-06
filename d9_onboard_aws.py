#!/usr/bin/python3

# *******************************************************************************
# Name: d9_onboard_aws.py
# Description: A automation script for CloudGuard that can onboard AWS accounts into 
# CloudGuard individually or sync AWS Organations accounts and Organizational Units
#
# Copywrite 2019, Check Point Software
# www.checkpoint.com
# *******************************************************************************

import json
import time
import os
import sys
import configparser
import argparse
from argparse import RawTextHelpFormatter
import requests
import boto3
import base64
from botocore.exceptions import ClientError
import string
from random import *
from time import sleep
from typing import Dict

from requests.auth import HTTPBasicAuth
from requests.exceptions import HTTPError
from datetime import datetime
from collections import namedtuple

print(f'\n:: CloudGuard AWS Onboarding with CFT Deployment Automation :: \nExecution time: {str(datetime.now())} \n')  # Got an error? You need Python 3.6 or later.

def add_aws_account_to_d9(name, arn, extid, readonly):
    if os.environ.get('CloudGuardRegion') == 'America':
        url = "https://api.dome9.com/v2/CloudAccounts"
    else:
        url = "https://api.eu1.dome9.com/v2/CloudAccounts"
    payload = {"name": name, "credentials": {"arn": arn, "secret": extid, "type": "RoleBased", "isReadOnly": readonly}, "fullProtection": "false"}

    print('\nAdding target AWS account to CloudGuard...')
    resp = http_request('post', url, payload, False)
    
    if resp.status_code == 201:
        resp = json.loads(resp.content)
        return resp['id']
    
    elif resp.status_code == 400:
        print('AWS Cloud Account already added or bad request. Please remove the account from CloudGuard before using this script.')
        print(payload)
    else:
        print('Error when attempting to add AWS account.')
        print(resp)
        return False      

def get_aws_accounts_from_d9():
    if os.environ.get('CloudGuardRegion') == 'America':
            url = "https://api.dome9.com/v2/CloudAccounts"
    else:
        url = "https://api.eu1.dome9.com/v2/CloudAccounts"
    payload = {}

    print('\nGetting list of AWS accounts already onboarded to CloudGuard...')
    resp = http_request('get', url, payload, False)
    
    if resp.status_code == 200:
        resp = json.loads(resp.content)
        return resp
    
    else:
        print('Error when attempting to get list of AWS accounts.')
        print(resp)
        return False

def create_ou_in_d9(name, parent_id):
    if os.environ.get('CloudGuardRegion') == 'America':
            url = "https://api.dome9.com/v2/organizationalunit"
    else:
        url = "https://api.eu1.dome9.com/v2/organizationalunit"

    payload = {"name":name,"parentId":parent_id}

    resp = http_request('post', url, payload, False)
    
    if resp.status_code == 200:
        resp = json.loads(resp.content)
        return resp['item']['id']
    
    else:
        print('Error when attempting to create OU in CloudGuard.')
        print(resp)
        return False

def attach_account_to_ou_in_d9(cloud_account_id, ou_id):        
    if OPTIONS.ignore_ou: # Ignore OU processing flag detected
        return True

    if os.environ.get('CloudGuardRegion') == 'America':
            url = "https://api.dome9.com/v2/cloudaccounts/organizationalunit/attach"
    else:
        url = "https://api.eu1.dome9.com/v2/cloudaccounts/organizationalunit/attach"

    payload = {"entries":[cloud_account_id],"organizationalUnitId":ou_id}

    print('\nAttaching Cloud Account to OU...')
    resp = http_request('post', url, payload, False)
    
    if resp.status_code == 200:
        resp = json.loads(resp.content)
        return resp
    
    else:
        print('Error when attempting to attach AWS account to CloudGuard OU.')
        print(resp)
        return False    
        
def get_aws_org_parent(orgclient, id):
    try: 
        parentresp = orgclient.list_parents(
            ChildId=id,
            MaxResults=10
        )['Parents'] 

        if parentresp[0]['Type'] == 'ORGANIZATIONAL_UNIT':
            ouresp = orgclient.describe_organizational_unit(
                OrganizationalUnitId=parentresp[0]['Id']
            )['OrganizationalUnit']
            return ouresp
        elif parentresp[0]['Type'] == 'ROOT':
            return False
    except ClientError as e:
        print(f'Unexpected error: {e}')
        
def get_aws_org_ou_list(orgclient, aws_account):
    ou_list = []
    current_parent = get_aws_org_parent(orgclient, aws_account)
    if current_parent:
        ou_list.append(current_parent['Name'])
    else:
        return ou_list
        
    while current_parent:
        current_parent = get_aws_org_parent(orgclient, current_parent['Id'])
        if current_parent:
            ou_list.insert(0, current_parent['Name'])

    if len(ou_list) > 5:
        print(f'ERROR: OUs have exceeded the depth limit of 5: \n{ou_list}')
        os._exit(1)
    else: 
        return ou_list

def get_cft_stack(cfclient, name):
    try: 
        resp = cfclient.describe_stacks(
        StackName=name,
        )['Stacks'] 
        return resp[0]
    except ClientError as e:
        print(f'Unexpected error: {e}')

def check_cft_stack_exists(cfclient, name):
    try:
        stacks = cfclient.list_stacks()['StackSummaries']
        for stack in stacks:
            if stack['StackName'] != name:
                continue
            else:
                if stack['StackStatus'] == 'DELETE_COMPLETE':
                    continue
                else:
                    return True
    except ClientError as e:
        print(f'Unexpected error: {e}')

def create_cft_stack(cfclient, name, cfturl, extid):
    try:
        resp = cfclient.create_stack(
            StackName=name,
            TemplateURL=cfturl,
            Parameters=[
                {
                    'ParameterKey': 'Externalid',
                    'ParameterValue': extid
                    },
            ],
            Capabilities=['CAPABILITY_IAM'],
            )
        return resp
    except ClientError as e:
        print(f'Unexpected error: {e}')
        return False

def process_organizatonal_units(aws_ou_list):
    if OPTIONS.ignore_ou: # Ignore OU processing flag detected
        return True

    # Get root OU list from CloudGuard
    if os.environ.get('CloudGuardRegion') == 'America':
            url = "https://api.dome9.com/v2/organizationalunit"
    else:
        url = "https://api.eu1.dome9.com/v2/organizationalunit"

    payload = {}
 
    resp = http_request('get', url, payload, True)

    if resp.status_code == 200:
        print('\nComparing Organizational Units...')
        root = json.loads(resp.content)
    
    else:
        print('Error when attempting to get OUs from CloudGuard.')
        print(resp)
        return False   
    
    current_d9_parent_ou = root[0]['children'] # Get OU children of root

    for depth, item in enumerate(aws_ou_list):
        missing_ou = True
        for idx, ou in enumerate(current_d9_parent_ou):
            if ou['item']['name'].lower() == aws_ou_list[depth].lower():
                print(f'  Found OU in CloudGuard: {aws_ou_list[depth]}')
                missing_ou = False
                last_ou = ou['item']['id']
                break

        if missing_ou: 
            oupath = 'ROOT/' + '/'.join(aws_ou_list)
            print(f'\CloudGuard OU(s) not found. \nCreating all OUs within path: {oupath} ...')
            missing_ou_depth = depth
            while missing_ou_depth < len(aws_ou_list):
                print(f'\nCreating OU: ROOT/{"/".join(aws_ou_list[:missing_ou_depth+1])}')
                if missing_ou_depth == 0:
                    last_ou = create_ou_in_d9(aws_ou_list[missing_ou_depth], None) #If Level 1 then parentId is Null
                else:
                    last_ou = create_ou_in_d9(aws_ou_list[missing_ou_depth], last_ou) #If Level 2 or below then use parentId
                missing_ou_depth += 1
            break
        else:            
            current_d9_parent_ou = current_d9_parent_ou[idx]['children']
    
    if aws_ou_list == []:
        return True
    else:
        return last_ou

def mode_crossaccount_onboard(stsclient):
    assume_role_arn = 'arn:aws:iam::' + OPTIONS.account_number + ':role/' + OPTIONS.role_name # Build role ARN of target account being onboarded to assume into
    print(f'\nAssuming Role into target account using ARN: {assume_role_arn}') 

    stsresp = stsclient.assume_role(
     RoleArn=assume_role_arn,
     RoleSessionName='DeployCloudGuardCFTSession',
     DurationSeconds=1800
     )
    cfclient = boto3.client('cloudformation',
     aws_access_key_id=stsresp['Credentials']['AccessKeyId'],
     aws_secret_access_key=stsresp['Credentials']['SecretAccessKey'],
     aws_session_token=stsresp['Credentials']['SessionToken'],
     region_name=OPTIONS.region_name
     )

    process_account(cfclient, OPTIONS.account_name)

def mode_organizations_onboard(orgclient, stsclient, cfclient):

    # function to print stats upon completion
    def _print_stats(discovered, successes, failures):
        print(f'\n\nOnboarding Statistics:\n  Discovered: {discovered}\n  Successes: {successes}\n  Failures: {failures}\n  Skipped: {(discovered - failures - successes)}')

    # Get AWS accounts from Orgs and iterate through the pages to create a list
    org_accounts_raw = orgclient.list_accounts(MaxResults=20) # Get first page of accounts, unknown if there are more pages yet
    org_accounts_pruned = []
    next_token = False
    count_successes = 0
    count_failures = 0

    for account in org_accounts_raw['Accounts']: 
        org_accounts_pruned.extend( [{'id': account['Id'], 'name': account['Name']}] )

    if 'NextToken' in org_accounts_raw: # More pages of accounts to process
        next_token = True

    while next_token:
        print('Fetching next page of accounts...')
        org_accounts_raw = orgclient.list_accounts(NextToken=org_accounts_raw['NextToken'], MaxResults=20)
        for account in org_accounts_raw['Accounts']:
            org_accounts_pruned.extend([{'id': account['Id'], 'name': account['Name']}])        
        if 'NextToken' in org_accounts_raw:
            next_token = True
        else:
            next_token = False #testing False, was True
            print('\nEnd of cloud acounts list.')
            break

    # Get AWS accounts from CloudGuard and iterate through to create a list    
    d9_aws_accounts_raw = get_aws_accounts_from_d9()
    d9_aws_accounts_pruned = {''}
    for account in d9_aws_accounts_raw:
        d9_aws_accounts_pruned.add(account['externalAccountNumber'])  

    unprotected_account_list = [d for d in org_accounts_pruned if (d['id']) not in d9_aws_accounts_pruned] # create list of AWS accounts not found in CloudGuard

    if len(unprotected_account_list) == 0:
        print("No unprotected accounts found.")
        return 0
        os._exit(1)
    else:
        print(f'\nFound the following unprotected AWS Accounts: ')
        for account in unprotected_account_list:
            print(f'  {account["id"]} | {account["name"]}')

    caller_account_number = boto3.client('sts', region_name=OPTIONS.region_name).get_caller_identity()['Account'] # Identify caller AWS account which needs to be processed without STS assume 

    for account in unprotected_account_list:
        print(f'\n*** Initiating onboarding for: {account["id"]} | {account["name"]}')
        aws_ou_list = get_aws_org_ou_list(orgclient, account['id'])    
        if account['id'] == caller_account_number and aws_ou_list: # OUs exist and AWS account number is the caller (local)
            d9_ou_id = process_organizatonal_units(aws_ou_list)
            d9_cloud_account_id = process_account(cfclient, account['name'])
            if d9_cloud_account_id:
                ou_attached = attach_account_to_ou_in_d9(d9_cloud_account_id, d9_ou_id)
        elif aws_ou_list: #OUs exist and AWS account number is not the callers
            assume_role_arn = 'arn:aws:iam::' + account['id'] + ':role/' + OPTIONS.role_name # Build role ARN of target account being onboarded to assume into
            print(f'\nAssuming Role into target account using ARN: {assume_role_arn}') 

            stsresp = stsclient.assume_role(
             RoleArn=assume_role_arn,
             RoleSessionName='DeployCloudGuardCFTSession',
             DurationSeconds=1800
             )
            cfclient = boto3.client('cloudformation',
             aws_access_key_id=stsresp['Credentials']['AccessKeyId'],
             aws_secret_access_key=stsresp['Credentials']['SecretAccessKey'],
             aws_session_token=stsresp['Credentials']['SessionToken'],
             region_name=OPTIONS.region_name
             )

            d9_ou_id = process_organizatonal_units(aws_ou_list)
            d9_cloud_account_id = process_account(cfclient, account['name'])
            if d9_cloud_account_id:
                ou_attached = attach_account_to_ou_in_d9(d9_cloud_account_id, d9_ou_id)
        ###
        elif not aws_ou_list and (account['id'] != caller_account_number): #OUs exist and AWS account number is not the callers
            assume_role_arn = 'arn:aws:iam::' + account['id'] + ':role/' + OPTIONS.role_name # Build role ARN of target account being onboarded to assume into
            print(f'\nAssuming Role into target account using ARN: {assume_role_arn}') 

            stsresp = stsclient.assume_role(
             RoleArn=assume_role_arn,
             RoleSessionName='DeployDome9CFTSession',
             DurationSeconds=1800
             )
            cfclient = boto3.client('cloudformation',
             aws_access_key_id=stsresp['Credentials']['AccessKeyId'],
             aws_secret_access_key=stsresp['Credentials']['SecretAccessKey'],
             aws_session_token=stsresp['Credentials']['SessionToken'],
             region_name=OPTIONS.region_name
             )

            d9_ou_id = process_organizatonal_units(aws_ou_list)
            d9_cloud_account_id = process_account(cfclient, account['name'])
            if d9_cloud_account_id:
                ou_attached = attach_account_to_ou_in_d9(d9_cloud_account_id, d9_ou_id)
        ###
        elif not aws_ou_list: # Account is in AWS Orgs root
            d9_cloud_account_id = process_account(cfclient, account['name'])

        if (not d9_cloud_account_id or not d9_ou_id or not ou_attached) and not OPTIONS.ignore_failures:
            count_failures += 1 
            print(f'\nError when attempting to onboard AWS account to CloudGuard. Exiting...')
            _print_stats(len(unprotected_account_list), count_successes, count_failures)
            os._exit(1)
        elif (d9_cloud_account_id == False or not d9_ou_id or not ou_attached) and OPTIONS.ignore_failures:
            print('\nError when attempting to onboard AWS account to CloudGuard. Continuing...')
            count_failures += 1
        elif d9_ou_id and d9_cloud_account_id and ou_attached:
            count_successes += 1
        
    _print_stats(len(unprotected_account_list), count_successes, count_failures)
    
def process_account(cfclient, aws_account_name):
    # Check if the CFT Stack exists from a previous run
    d9stack = 'CloudGuardPolicyAutomated'
    if check_cft_stack_exists(cfclient, d9stack):
        print('\nStack exists.  Perhaps this script has already been run?')
        return False
    else:
        print('\nCreating CloudFormation Stack...')
    
    print('\nProvisioning the CloudFormation stack in AWS...')
    extid = ''.join(choice(string.ascii_letters + string.digits) for _ in range(24))
    stack_created = create_cft_stack(cfclient, d9stack, cft_s3_url, extid)

    #CHECK CFT STATUS
    t = 0
    while t < 20:
        t += 1
        stack = get_cft_stack(cfclient, d9stack)
        if stack['StackStatus'] not in ['CREATE_IN_PROGRESS','CREATE_COMPLETE']:
            print(f'Something went wrong during CFT stack deployment: {stack["StackStatus"]}')
            return False
        elif stack['StackStatus'] == 'CREATE_COMPLETE':
            print('Success! Stack created.')
            break
        else:
            print(f'... Try {t}/20: {stack["StackStatus"]}')
            sleep(15)            
    
    # Get CFT Stack info to pull the Role ARN
    cftstack = get_cft_stack(cfclient, d9stack)
    rolearn = False
    for output in cftstack['Outputs']:
        if output['OutputKey'] == 'RoleARNID':
            rolearn=output['OutputValue']

    # Add the AWS account to CloudGuard
    d9_account_added = add_aws_account_to_d9(aws_account_name, rolearn, extid, d9readonly)
    print(f'Added: {rolearn.split(":")[4]} | {aws_account_name} | {d9_account_added}')
    return d9_account_added
    
def http_request(request_type, url, payload, silent): 

    # request_type = post/delete/get
    request_type = request_type.lower()
    # silent = True/False
    headers = {'content-type': 'application/json'}
    resp = ''
    try:
        if request_type.lower() == 'post':
            resp = requests.post(url, auth=HTTPBasicAuth(d9credentials['AccessId'], d9credentials['Secret']), json=payload, headers=headers)
        elif request_type.lower() == 'delete':
            resp = requests.delete(url, auth=HTTPBasicAuth(d9credentials['AccessId'], d9credentials['Secret']), json=payload, headers=headers)
        elif request_type.lower() == 'get':
            resp = requests.get(url, auth=HTTPBasicAuth(d9credentials['AccessId'], d9credentials['Secret']), json=payload, headers=headers)
        else:
            print('Request type not supported.')
            return False
        
        resp.raise_for_status()
    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}') 
    except Exception as err:
        print(f'Other error occurred: {err}')  
    else:
        if not silent:
            print('Success!')
    
    return resp

def main(event, context):
    global d9credentials, d9secretname, cft_s3_url, d9readonly, mode, OPTIONS

    mode = os.environ.get('mode')
    d9secretname = "CloudGuardAPIKeys"
    d9credentials = {}

    OPTIONS = {}
    OPTIONS['role_name'] = os.environ.get('role_name')
    OPTIONS['region_name'] = os.environ.get('region_name')
    OPTIONS['d9mode'] = os.environ.get('d9mode')
    OPTIONS['ignore_ou'] = False
    OPTIONS['ignore_failures'] = os.environ.get('ignore_failures')

    OPTIONS = namedtuple("Options", OPTIONS.keys())(*OPTIONS.values())
    
    # load config file
    config = configparser.ConfigParser()
    config.read("./d9_onboard_aws.conf")
    
    secret_manager_client = boto3.client(service_name='secretsmanager',region_name=OPTIONS.region_name)

    try:
        print('Getting CloudGuard credentials from AWS SecretManager')
        secret_value_response = secret_manager_client.get_secret_value(SecretId=d9secretname)
        print(secret_value_response)
    except Exception as e:
        print(f"Could not get secret value for SecretId: {d9secretname}. Error: {repr(e)}")
        raise
    else:
        if 'SecretString' in secret_value_response:
            secret = secret_value_response['SecretString']
            d9credentials=json.loads(secret)
            print(d9credentials)
        else:
            decoded_binary_secret = base64.b64decode(secret_value_response['SecretBinary'])
            d9credentials=json.loads(decoded_binary_secret)

    # Get AWS creds for the client. Region is needed for CFT deployment location.
    print('\nCreating AWS service clients...\n')
    cfclient = boto3.client('cloudformation', region_name=OPTIONS.region_name)
    try: # Check for successful authentication
        cfclient.list_stacks()      
    except ClientError as e:
        print(f'ERROR: Unable to authenticate to AWS using environment variables or IAM role.')
        os._exit(1)

    if mode == 'crossaccount':
        stsclient = boto3.client('sts', region_name=OPTIONS.region_name)
    elif mode == 'organizations':
        orgclient = boto3.client('organizations', region_name=OPTIONS.region_name)   
        stsclient = boto3.client('sts', region_name=OPTIONS.region_name)

    # Deploy the respective CFT for the mode
    if os.environ.get('CloudGuardRegion') == 'America':
        if OPTIONS.d9mode == ('readonly'):
            cft_s3_url = config.get('aws', 'cft_s3_url_readonly')
            d9readonly = True
        elif OPTIONS.d9mode == ('readwrite'):
            cft_s3_url = config.get('aws', 'cft_s3_url_readwrite')
            d9readonly = False
        else:
            print ('ERROR: Invalid CloudGuard mode.')
            os._exit(1)
    else:
        if OPTIONS.d9mode == ('readonly'):
            cft_s3_url = config.get('aws', 'cft_s3_url_readonly_eu')
            d9readonly = True
        elif OPTIONS.d9mode == ('readwrite'):
            cft_s3_url = config.get('aws', 'cft_s3_url_readwrite_eu')
            d9readonly = False
        else:
            print ('ERROR: Invalid CloudGuard mode.')
            os._exit(1)
			
    if mode == 'local' and OPTIONS.account_name and OPTIONS.region_name and OPTIONS.d9mode:
        process_account(cfclient, OPTIONS.account_name)
    elif mode == 'crossaccount' and OPTIONS.account_number and OPTIONS.account_name and OPTIONS.role_name and OPTIONS.region_name and OPTIONS.d9mode:
        mode_crossaccount_onboard(stsclient)
    elif mode == 'organizations' and OPTIONS.role_name and OPTIONS.region_name and OPTIONS.d9mode:
        if OPTIONS.ignore_ou: # Ignore OU processing flag detected
            print('\nIgnore Organizational Units flag is set to True. All AWS accounts will be placed in root.')
        mode_organizations_onboard(orgclient, stsclient, cfclient)
    else:
        os._exit(1)
    return 0

if __name__ == '__main__': main()
