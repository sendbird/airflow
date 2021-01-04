import os
import yaml
import argparse
import boto3
import subprocess

from sendbird_common.regions import SB_REGION_TO_AWS_REGION

KUBECONFIG_PATH = os.path.join(os.path.expanduser('~'), '.kube', 'config')
CLUSTER_NAME_FORMAT = 'dataplatform-airflow_{airflow_type}-{region}-dw'


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

aws_session = boto3.session.Session()


def exec_command(commands, timeout=3):
  try:
    output = subprocess.check_output(
      commands, stderr=subprocess.STDOUT, shell=True, timeout=timeout,
      universal_newlines=True)
  except subprocess.CalledProcessError as exc:
    print('`{}` has been failed with error:'.format(commands), exc.returncode, exc.output)
    raise
  print('`{}` has been succeed. output: {}'.format(commands, output))


def setup_kubeconfig(aws_region, airflow_type, cluster_name=None):
  if not cluster_name:
    cluster_name = CLUSTER_NAME_FORMAT.format(airflow_type=airflow_type, region=SHORTENED_AWS_REGIONS[aws_region])
  unified_name = '{}.{}.eksctl.io'.format(cluster_name, aws_region)
  configs = None

  if os.path.isfile(KUBECONFIG_PATH):
    file = open('/Users/harley.son/.kube/config')
    configs = yaml.load(file, Loader=yaml.FullLoader)

  if configs:
    try:
      if any(d['name'] == unified_name for d in configs['clusters']):
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
        'command': 'aws-iam-authenticator',
        "args": ["token", "-i", cluster_name]
      }
    }
  })
  config_text = yaml.dump(configs, default_flow_style=False)
  open(KUBECONFIG_PATH, 'w').write(config_text)

  print('Configuration setup has been done for the cluster {}'.format(cluster_name))
  return unified_name


def deploy(region, aws_region, airflow_type, cluster_name):
  context_name = setup_kubeconfig(aws_region, airflow_type, cluster_name)

  exec_command(['kubectl config use-context {}'.format(context_name)])
  exec_command(['helm upgrade -i airflow {} --namespace {}'.format(
    os.path.dirname(os.path.abspath(__file__)), region
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

  if not args.aws_region:
    try:
      args.aws_region = SB_REGION_TO_AWS_REGION[args.region]
    except KeyError:
      raise argparse.ArgumentError('Cannot find AWS region from SendBird region. Specify <aws_region>')

  return args


def main():
  args = parse_args()

  print('Regions to deploy: {}'.format(args.region))
  for region in args.region:
    deploy(
      region=region,
      aws_region=args.aws_region,
      airflow_type=args.airflow_type,
      cluster_name=args.cluster_name,
    )


if __name__ == '__main__':
  main()
