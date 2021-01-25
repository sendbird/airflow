import os
import yaml
import argparse
import boto3
import subprocess

from sendbird_common.regions import SB_REGION_TO_AWS_REGION

KUBECONFIG_PATH = os.path.join(os.path.expanduser('~'), '.kube', 'config')
# CLUSTER_NAME_FORMAT = 'dataplatform-airflow_{airflow_type}-{region}-dw'
CLUSTER_NAME_FORMAT = 'dataplatformstaging-airflow-{airflow_type}'

SHORTENED_AWS_REGIONS = {
  'us-east-1': 'use1',
  'us-gov-east-1': 'usgove1',
  'ap-northeast-1': 'apne1',
  'ap-northeast-2': 'apne2',
  'ap-southeast-1': 'apse1',
  'ap-south-1': 'aps1',
  'ap-southeast-2': 'apse2',
  'eu-central-1': 'euc1',
  'us-west-2': 'usw2',
}


ACCOUNT_IDS = {
  'dev': '242864343139',
  'stg': '232797014574',
  'prod': '012481551608',
}

aws_session = None


def setup_boto3_session_assume_role(env):
  account_id = ACCOUNT_IDS[env]

  role_arn = 'arn:aws:iam::{account_id}:role/data-engineer-dataeng-{env}'\
      .format(account_id=account_id, env=env)

  sts_client = boto3.client('sts')
  assumed_role = sts_client.assume_role(
    RoleArn=role_arn, RoleSessionName='dataeng-{}'.format(env)
  )

  print(assumed_role)
  return boto3.session.Session(
    aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
    aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
    aws_session_token=assumed_role['Credentials']['SessionToken'],
  )


def exec_command(commands, timeout=3):
  try:
    output = subprocess.check_output(
      commands, stderr=subprocess.STDOUT, shell=True, timeout=timeout,
      universal_newlines=True)
  except subprocess.CalledProcessError as exc:
    print('`{}` has been failed with error:'.format(commands), exc.returncode, exc.output)
    raise
  print('`{}` has been succeed. output: {}'.format(commands, output))


def setup_kubeconfig(aws_region, airflow_type, env, cluster_name=None):
  if not cluster_name:
    cluster_name = CLUSTER_NAME_FORMAT.format(airflow_type=airflow_type, region=SHORTENED_AWS_REGIONS[aws_region])
  unified_name = 'arn:aws:eks:{aws_region}:{aws_account}:cluster/{cluster_name}'.format(
    aws_region=aws_region, aws_account=ACCOUNT_IDS[env], cluster_name=cluster_name,
  )
  configs = None

  if os.path.isfile(KUBECONFIG_PATH):
    file = open(KUBECONFIG_PATH)
    configs = yaml.load(file, Loader=yaml.FullLoader)

  if configs:
    try:
      if any(cluster_name in d['name'] for d in configs['clusters']):
        print('The configuration for the cluster {} already exists.'.format(cluster_name))
        return unified_name
    except:
      print('The {} file has wrong format.'.format(KUBECONFIG_PATH))
      raise
  else:
    configs = {
      'apiVersion': 'v1',
      'kind': 'Config',
      'clusters': [],
      'contexts': [],
      'current-context': '',
      'preferences': {},
      'users': [],
    }

  eks = aws_session.client('eks', region_name=aws_region)
  cluster_name = CLUSTER_NAME_FORMAT.format(airflow_type=airflow_type, region=SHORTENED_AWS_REGIONS[aws_region])

  cluster = eks.describe_cluster(name=cluster_name)
  cluster_cert = cluster["cluster"]["certificateAuthority"]["data"]
  cluster_endpoint = cluster["cluster"]["endpoint"]

  configs['clusters'].append({
    'cluster': {
      'server': str(cluster_endpoint),
      'certificate-authority-data': str(cluster_cert),
    },
    'name': unified_name,
  })
  configs['contexts'].append({
    'context': {
      'cluster': unified_name,
      'user': unified_name,
    },
    'name': unified_name,
  })
  configs['users'].append({
    'name': unified_name,
    'user': {
      'exec': {
        'apiVersion': 'client.authentication.k8s.io/v1alpha1',
        'command': 'aws',
        'args': [
          '--region', aws_region,
          'eks',
          'get-token',
          '--cluster-name', cluster_name
        ]
      }
    }
  })
  config_text = yaml.dump(configs, default_flow_style=False)
  open(KUBECONFIG_PATH, 'w').write(config_text)

  print('Configuration setup has been done for the cluster {}'.format(cluster_name))
  return unified_name


def deploy(region, aws_region, airflow_type, cluster_name, env):
  context_name = setup_kubeconfig(aws_region, airflow_type, env, cluster_name)

  exec_command(['kubectl config use-context {}'.format(context_name)])
  exec_command(['helm upgrade -i -f {} airflow {} --namespace {}'.format(
    'values_{}.yaml'.format(region), os.path.dirname(os.path.abspath(__file__)), region
  )], timeout=600)
  print('Local chart has been deployed to the namespace: {} context: {}'.format(region, context_name))


def parse_args():
  parser = argparse.ArgumentParser()
  parser.add_argument('region', action='store', help='Region', nargs='+')
  parser.add_argument('--airflow-type', '-t', action='store', default='local', help='Type of airflow cluster',
                      choices=['local', 'central'])
  parser.add_argument('--cluster-name', '-c', action='store', required=False, help='Kubernetes cluster name')
  parser.add_argument('--aws-region', '-r', action='store', required=False, help='AWS Region (e.g. ap-northeast-1)')
  parser.add_argument('--env', '-e', action='store', default='prod', help='AWS Environment to deploy',
                      choices=['prod', 'stg', 'dev'])
  args = parser.parse_args()

  return args


def main():
  args = parse_args()

  try:
    global aws_session
    aws_session = setup_boto3_session_assume_role(env=args.env)
  except Exception as e:
    print("Unable to setup boto3 session: {}".format(e))
    return

  print('Regions to deploy: {}'.format(args.region))
  for region in args.region:
    aws_region = args.aws_region
    if not aws_region:
      try:
        aws_region = SB_REGION_TO_AWS_REGION[region]
      except KeyError:
        raise argparse.ArgumentError('Cannot find AWS region from SendBird region. Specify <aws_region>')

    deploy(
      region=region,
      aws_region=aws_region,
      airflow_type=args.airflow_type,
      cluster_name=args.cluster_name,
      env=args.env,
    )


if __name__ == '__main__':
  main()
