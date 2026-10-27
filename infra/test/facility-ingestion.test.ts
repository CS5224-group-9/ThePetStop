import * as cdk from 'aws-cdk-lib/core';
import { Match, Template } from 'aws-cdk-lib/assertions';
import { DataStack } from '../lib/data-stack';
import { FacilityIngestionStack } from '../lib/facility-ingestion-stack';
import { NetworkStack } from '../lib/network-stack';

const app = new cdk.App();
const env = { account: '123456789012', region: 'ap-southeast-1' };
const network = new NetworkStack(app, 'IngestionNetwork', { env });
const data = new DataStack(app, 'IngestionData', { env, network });
const template = Template.fromStack(
  new FacilityIngestionStack(app, 'Ingestion', { env, network, data }),
);

test('ingestion storage is private, versioned and retained', () => {
  template.hasResourceProperties('AWS::S3::Bucket', {
    VersioningConfiguration: { Status: 'Enabled' },
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
    BucketEncryption: Match.anyValue(),
  });
  template.hasResource('AWS::S3::Bucket', { DeletionPolicy: 'Retain' });
});

test('queues and asynchronous invocations retain failed work', () => {
  template.hasResourceProperties('AWS::SQS::Queue', {
    FifoQueue: true,
    VisibilityTimeout: 900,
    RedrivePolicy: { maxReceiveCount: 5, deadLetterTargetArn: Match.anyValue() },
  });
  template.resourceCountIs('AWS::Lambda::EventInvokeConfig', 3);
  template.hasResourceProperties('AWS::Lambda::EventSourceMapping', { BatchSize: 1 });
});

test('internet workers are outside the VPC and only loader gets DB secrets', () => {
  const functions = Object.values(template.findResources('AWS::Lambda::Function')).filter(
    (row) => row.Properties.PackageType === 'Image',
  );
  expect(functions).toHaveLength(5);
  const loaders = functions.filter((row) => row.Properties.VpcConfig);
  expect(loaders).toHaveLength(1);
  expect(loaders[0].Properties.ImageConfig.Command).toEqual(['facilities.ingestion.handlers.load']);
  expect(loaders[0].Properties.ReservedConcurrentExecutions).toBe(2);
  for (const row of functions.filter((row) => !row.Properties.VpcConfig)) {
    expect(row.Properties.Environment.Variables.DB_SECRET_ARN).toBeUndefined();
    expect(row.Properties.Environment.Variables.AWS_ENDPOINT_URL).toBeUndefined();
  }
});

test('schedules stay disabled and alarms publish to the alert topic', () => {
  template.resourceCountIs('AWS::Events::Rule', 3);
  template.allResourcesProperties('AWS::Events::Rule', { State: 'DISABLED' });
  template.hasResourceProperties('AWS::CloudWatch::Alarm', { AlarmActions: Match.anyValue() });
  template.hasResourceProperties('AWS::CloudWatch::Alarm', {
    MetricName: 'DataAgeHours',
    TreatMissingData: 'breaching',
  });
  template.resourceCountIs('AWS::CloudWatch::Dashboard', 1);
});
