import * as cdk from 'aws-cdk-lib/core';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { ApiStack } from '../lib/api-stack';
import { AuthStack } from '../lib/auth-stack';
import { DataStack } from '../lib/data-stack';
import { NetworkStack } from '../lib/network-stack';
import { StorageStack } from '../lib/storage-stack';

function synth() {
  const app = new cdk.App();
  const env = { account: '123456789012', region: 'ap-southeast-1' };
  const network = new NetworkStack(app, 'Network', { env });
  const data = new DataStack(app, 'Data', { env, network });
  const storage = new StorageStack(app, 'Storage', { env });
  const auth = new AuthStack(app, 'Auth', { env, frontendUrl: storage.frontendUrl });
  const api = new ApiStack(app, 'Api', { env, network, data, auth, storage });
  return {
    network: Template.fromStack(network),
    data: Template.fromStack(data),
    storage: Template.fromStack(storage),
    auth: Template.fromStack(auth),
    api: Template.fromStack(api),
  };
}

const t = synth();

test('VPC has no NAT gateway or internet gateway', () => {
  t.network.resourceCountIs('AWS::EC2::NatGateway', 0);
  t.network.resourceCountIs('AWS::EC2::InternetGateway', 0);
  t.network.resourceCountIs('AWS::EC2::VPCEndpoint', 2);
});

test('database is a private db.t4g.micro PostgreSQL 16', () => {
  t.data.hasResourceProperties('AWS::RDS::DBInstance', {
    Engine: 'postgres',
    EngineVersion: '16',
    DBInstanceClass: 'db.t4g.micro',
    PubliclyAccessible: false,
    MultiAZ: false,
    BackupRetentionPeriod: 7,
  });
});

test('every bucket blocks public access', () => {
  const buckets = t.storage.findResources('AWS::S3::Bucket');
  expect(Object.keys(buckets)).toHaveLength(3);
  for (const bucket of Object.values(buckets)) {
    expect(bucket.Properties.PublicAccessBlockConfiguration).toEqual({
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    });
  }
});

test('Cognito client is public with code flow and has both groups', () => {
  t.auth.hasResourceProperties('AWS::Cognito::UserPoolClient', {
    GenerateSecret: false,
    AllowedOAuthFlows: ['code'],
  });
  for (const name of ['owner', 'merchant']) {
    t.auth.hasResourceProperties('AWS::Cognito::UserPoolGroup', { GroupName: name });
  }
});

test('catch-all route requires a JWT; health and preflights are public', () => {
  t.api.hasResourceProperties('AWS::ApiGatewayV2::Route', {
    RouteKey: '$default',
    AuthorizationType: 'JWT',
  });
  for (const routeKey of ['GET /api/v1/health/{proxy+}', 'OPTIONS /{proxy+}']) {
    t.api.hasResourceProperties('AWS::ApiGatewayV2::Route', {
      RouteKey: routeKey,
      AuthorizationType: 'NONE',
    });
  }
  const protectedRoutes = Object.values(t.api.findResources('AWS::ApiGatewayV2::Route'))
    .filter((r) => r.Properties.AuthorizationType === 'JWT')
    .map((r) => r.Properties.RouteKey);
  expect(protectedRoutes).toEqual(['$default']);
});

test('API Lambdas run in the VPC with 14-day logs', () => {
  t.api.resourceCountIs('AWS::Lambda::Function', 2);
  t.api.allResourcesProperties('AWS::Lambda::Function', {
    VpcConfig: Match.objectLike({ SubnetIds: Match.anyValue() }),
  });
  t.api.allResourcesProperties('AWS::Logs::LogGroup', { RetentionInDays: 14 });
});
