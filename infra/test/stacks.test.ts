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

test('PetFiles bucket expires old versions and aborts incomplete uploads', () => {
  t.storage.hasResourceProperties('AWS::S3::Bucket', {
    VersioningConfiguration: { Status: 'Enabled' },
    LifecycleConfiguration: {
      Rules: Match.arrayWith([
        Match.objectLike({
          Status: 'Enabled',
          NoncurrentVersionExpiration: { NoncurrentDays: 7 },
          ExpiredObjectDeleteMarker: true,
          AbortIncompleteMultipartUpload: { DaysAfterInitiation: 1 },
        }),
      ]),
    },
  });
  const petFiles = Object.values(
    t.storage.findResources('AWS::S3::Bucket', {
      Properties: { LifecycleConfiguration: Match.anyValue() },
    }),
  );
  expect(petFiles).toHaveLength(1);
  expect(petFiles[0].Properties.VersioningConfiguration).toEqual({ Status: 'Enabled' });
  expect(petFiles[0].Properties.CorsConfiguration.CorsRules[0].AllowedHeaders).toEqual([
    'content-type',
  ]);
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
  // Pet routes have no public route; they stay behind the $default JWT route
  const routeKeys = Object.values(t.api.findResources('AWS::ApiGatewayV2::Route')).map(
    (r) => r.Properties.RouteKey as string,
  );
  for (const routeKey of routeKeys) {
    expect(routeKey).not.toMatch(/pets|reminders/);
  }
});

test('API Lambdas run in the VPC with 14-day logs', () => {
  t.api.resourceCountIs('AWS::Lambda::Function', 2);
  t.api.allResourcesProperties('AWS::Lambda::Function', {
    VpcConfig: Match.objectLike({ SubnetIds: Match.anyValue() }),
  });
  t.api.allResourcesProperties('AWS::Logs::LogGroup', { RetentionInDays: 14 });
});

test('both Lambdas get the pet files bucket name', () => {
  t.api.allResourcesProperties('AWS::Lambda::Function', {
    Environment: { Variables: Match.objectLike({ PET_FILES_BUCKET: Match.anyValue() }) },
  });
});

test('only the API function can read and write pet files, by object, without listing', () => {
  interface Statement {
    Action: string | string[];
    Resource: unknown;
  }
  const actionsOf = (s: Statement) => (Array.isArray(s.Action) ? s.Action : [s.Action]);
  const policies = Object.values(t.api.findResources('AWS::IAM::Policy'));
  const statements = policies.flatMap((p) =>
    (p.Properties.PolicyDocument.Statement as Statement[]).map((statement) => ({
      statement,
      roles: p.Properties.Roles as unknown[],
    })),
  );

  const s3Statements = statements.filter(({ statement }) =>
    actionsOf(statement).some((a) => a.startsWith('s3:')),
  );
  expect(s3Statements).toHaveLength(1);
  const [{ statement, roles }] = s3Statements;
  expect([...actionsOf(statement)].sort()).toEqual([
    's3:DeleteObject',
    's3:GetObject',
    's3:PutObject',
  ]);
  expect(JSON.stringify(statement.Resource)).toContain('/pets/*');
  expect(roles).toEqual([{ Ref: expect.stringMatching(/^ApiFunctionServiceRole/) }]);

  for (const { statement: s } of statements) {
    for (const action of actionsOf(s)) {
      expect(action).not.toMatch(/^s3:(List|GetBucket|\*$)/);
    }
  }
});
