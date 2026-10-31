import * as path from 'node:path';
import * as cdk from 'aws-cdk-lib/core';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as destinations from 'aws-cdk-lib/aws-lambda-destinations';
import * as sources from 'aws-cdk-lib/aws-lambda-event-sources';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as notifications from 'aws-cdk-lib/aws-s3-notifications';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as sqs from 'aws-cdk-lib/aws-sqs';
import { Construct } from 'constructs';
import { DataStack } from './data-stack';
import { NetworkStack } from './network-stack';
import { twoWeekLogGroup } from './log-group';

export interface FacilityIngestionStackProps extends cdk.StackProps {
  network: NetworkStack;
  data: DataStack;
  enableSchedules?: boolean;
}

export class FacilityIngestionStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: FacilityIngestionStackProps) {
    super(scope, id, props);
    const bucket = new s3.Bucket(this, 'Artifacts', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      lifecycleRules: [
        { prefix: 'cache/', expiration: cdk.Duration.days(90) },
        { noncurrentVersionExpiration: cdk.Duration.days(30) },
      ],
    });
    const queueProps = {
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
      retentionPeriod: cdk.Duration.days(14),
      visibilityTimeout: cdk.Duration.minutes(15),
    };
    const workDlq = new sqs.Queue(this, 'WorkDlq', { ...queueProps, fifo: true });
    const work = new sqs.Queue(this, 'Work', {
      ...queueProps,
      retentionPeriod: cdk.Duration.days(4),
      fifo: true,
      deadLetterQueue: { queue: workDlq, maxReceiveCount: 5 },
    });
    const captureDlq = new sqs.Queue(this, 'FailureCaptureDlq', queueProps);
    const failures = new sqs.Queue(this, 'InvocationFailures', {
      ...queueProps,
      deadLetterQueue: { queue: captureDlq, maxReceiveCount: 5 },
    });
    const oneMap = new secretsmanager.Secret(this, 'OneMapCredentials', {
      description: 'Populate email/password before enabling facility ingestion schedules',
      secretObjectValue: {
        email: cdk.SecretValue.unsafePlainText(''),
        password: cdk.SecretValue.unsafePlainText(''),
      },
    });
    const common = { FACILITY_SYNC_BUCKET: bucket.bucketName };
    const makeFunction = (stage: string, environment: Record<string, string>, inVpc = false) =>
      new lambda.DockerImageFunction(this, `${stage}Function`, {
        code: lambda.DockerImageCode.fromImageAsset(path.join(__dirname, '../../backend'), {
          platform: Platform.LINUX_AMD64,
          cmd: [`facilities.ingestion.handlers.${stage}`],
        }),
        architecture: lambda.Architecture.X86_64,
        memorySize: 1024,
        timeout: cdk.Duration.seconds(['fetch', 'reconcile'].includes(stage) ? 180 : 120),
        environment: { ...common, ...environment },
        logGroup: twoWeekLogGroup(this, `${stage}Logs`),
        ...(inVpc
          ? {
              vpc: props.network.vpc,
              vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
              securityGroups: [props.network.appSecurityGroup],
            }
          : {}),
      });
    const fetch = makeFunction('fetch', { GEOCODE_QUEUE_URL: work.queueUrl });
    const geocode = makeFunction('geocode', {
      GEOCODE_QUEUE_URL: work.queueUrl,
      ONEMAP_SECRET_ARN: oneMap.secretArn,
      ONEMAP_REQUESTS_PER_MINUTE: '75',
      GEOCODE_CACHE_MAX_AGE_DAYS: '90',
    });
    const load = makeFunction(
      'load',
      {
        DJANGO_SECRET_KEY_ARN: props.data.djangoSecretKey.secretArn,
        DB_SECRET_ARN: props.data.database.secret!.secretArn,
        FACILITY_MAX_DEACTIVATION_FRACTION: '0.2',
      },
      true,
    );
    const reconcile = makeFunction('reconcile', {
      GEOCODE_QUEUE_URL: work.queueUrl,
      GEOCODE_DLQ_URL: workDlq.queueUrl,
      FACILITY_MAX_RUN_AGE_HOURS: '24',
    });
    const failure = makeFunction('failure', {});
    const allow = (fn: lambda.IFunction, prefixes: string[], write: boolean) => {
      fn.addToRolePolicy(
        new iam.PolicyStatement({
          actions: write ? ['s3:PutObject'] : ['s3:GetObject', 's3:GetObjectVersion'],
          resources: prefixes.map((prefix) => bucket.arnForObjects(`${prefix}/*`)),
        }),
      );
    };
    const producers = [fetch, reconcile];
    for (const fn of producers) {
      allow(
        fn,
        [
          'control',
          'leases',
          'pending',
          'raw',
          'runs',
          'status',
          'failed',
          'results',
          'ready',
          'loaded',
          'projected',
          'recovery',
          'deferred',
        ],
        false,
      );
      allow(
        fn,
        [
          'control',
          'leases',
          'pending',
          'raw',
          'runs',
          'status',
          'failed',
          'ready',
          'recovery',
          'deferred',
          'work-failures',
        ],
        true,
      );
      fn.addToRolePolicy(
        new iam.PolicyStatement({ actions: ['s3:ListBucket'], resources: [bucket.bucketArn] }),
      );
      work.grantSendMessages(fn);
    }
    reconcile.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['s3:DeleteObject'],
        resources: [bucket.arnForObjects('failed/*')],
      }),
    );
    workDlq.grantConsumeMessages(reconcile);
    allow(
      geocode,
      [
        'control',
        'pending',
        'runs',
        'cache',
        'coordination',
        'results',
        'ready',
        'failed',
        'status',
      ],
      false,
    );
    allow(
      geocode,
      ['cache', 'coordination', 'results', 'ready', 'status', 'failed', 'quarantine'],
      true,
    );
    geocode.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['s3:ListBucket'],
        resources: [bucket.bucketArn],
      }),
    );
    oneMap.grantRead(geocode);
    geocode.addEventSource(new sources.SqsEventSource(work, { batchSize: 1 }));
    allow(load, ['status', 'ready', 'approvals'], false);
    allow(load, ['loaded', 'projected', 'status', 'failed', 'quarantine'], true);
    load.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['s3:ListBucket'],
        resources: [bucket.bucketArn],
      }),
    );
    props.data.database.secret!.grantRead(load);
    props.data.djangoSecretKey.grantRead(load);
    allow(failure, ['status', 'failed', 'invocation-failures'], true);
    failure.addEventSource(new sources.SqsEventSource(failures, { batchSize: 1 }));
    bucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new notifications.LambdaDestination(load),
      { prefix: 'ready/' },
    );
    bucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new notifications.LambdaDestination(load),
      { prefix: 'status/' },
    );
    for (const fn of [fetch, load, reconcile]) {
      fn.configureAsyncInvoke({
        retryAttempts: 2,
        maxEventAge: cdk.Duration.hours(1),
        onFailure: new destinations.SqsDestination(failures),
      });
    }
    for (const source of ['vet', 'pet_shop']) {
      new events.Rule(this, `${source}Weekly`, {
        enabled: props.enableSchedules ?? false,
        schedule: events.Schedule.cron({
          minute: '0',
          hour: source === 'vet' ? '18' : '19',
          weekDay: 'SUN',
        }),
        targets: [
          new targets.LambdaFunction(fetch, {
            event: events.RuleTargetInput.fromObject({
              operation: 'start',
              source,
              execution_id: events.EventField.eventId,
            }),
            deadLetterQueue: failures,
          }),
        ],
      });
    }
    new events.Rule(this, 'ReconcileSchedule', {
      enabled: props.enableSchedules ?? false,
      schedule: events.Schedule.rate(cdk.Duration.minutes(15)),
      targets: [
        new targets.LambdaFunction(reconcile, {
          event: events.RuleTargetInput.fromObject({}),
          deadLetterQueue: failures,
        }),
      ],
    });
    const alerts = new sns.Topic(this, 'Alerts');
    const alarm = (
      name: string,
      metric: cloudwatch.IMetric,
      threshold = 1,
      missing = cloudwatch.TreatMissingData.NOT_BREACHING,
    ) => {
      const item = new cloudwatch.Alarm(this, name, {
        metric,
        threshold,
        evaluationPeriods: 1,
        comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treatMissingData: missing,
      });
      item.addAlarmAction(new actions.SnsAction(alerts));
    };
    for (const [name, queue] of [
      ['WorkDlq', workDlq],
      ['InvocationFailures', failures],
      ['FailureCaptureDlq', captureDlq],
    ] as const) {
      alarm(`${name}NotEmpty`, queue.metricApproximateNumberOfMessagesVisible());
    }
    alarm('OldQueuedWork', work.metricApproximateAgeOfOldestMessage(), 1800);
    alarm(
      'QuarantinedMessages',
      new cloudwatch.Metric({
        namespace: 'PetStop/FacilityIngestion',
        metricName: 'QuarantinedMessages',
        statistic: 'Sum',
      }),
    );
    for (const [name, fn] of [
      ['Fetch', fetch],
      ['Geocode', geocode],
      ['Load', load],
      ['Reconcile', reconcile],
      ['Failure', failure],
    ] as const) {
      alarm(`${name}Errors`, fn.metricErrors({ statistic: 'Sum' }));
    }
    for (const source of ['vet', 'pet_shop']) {
      alarm(
        `${source}RunFailures`,
        new cloudwatch.Metric({
          namespace: 'PetStop/FacilityIngestion',
          metricName: 'Failures',
          dimensionsMap: { source },
          statistic: 'Sum',
        }),
      );
      alarm(
        `${source}StaleData`,
        new cloudwatch.Metric({
          namespace: 'PetStop/FacilityIngestion',
          metricName: 'DataAgeHours',
          dimensionsMap: { source },
          statistic: 'Maximum',
          period: cdk.Duration.minutes(30),
        }),
        192,
        cloudwatch.TreatMissingData.BREACHING,
      );
    }
    new cloudwatch.Dashboard(this, 'Dashboard', {
      widgets: [
        [
          new cloudwatch.GraphWidget({
            title: 'Ingestion work and failures',
            left: [
              work.metricApproximateNumberOfMessagesVisible(),
              workDlq.metricApproximateNumberOfMessagesVisible(),
              failures.metricApproximateNumberOfMessagesVisible(),
            ],
          }),
        ],
      ],
    });
    new cdk.CfnOutput(this, 'ArtifactBucket', { value: bucket.bucketName });
    new cdk.CfnOutput(this, 'OneMapSecretArn', { value: oneMap.secretArn });
    new cdk.CfnOutput(this, 'AlertTopicArn', { value: alerts.topicArn });
    const operator = new iam.ManagedPolicy(this, 'RecoveryOperatorPolicy', {
      description: 'Attach to the approved operator role for snapshot review and run recovery',
      statements: [
        new iam.PolicyStatement({
          actions: ['s3:GetObject'],
          resources: [
            'ready',
            'failed',
            'raw',
            'runs',
            'status',
            'quarantine',
            'invocation-failures',
            'work-failures',
          ].map((prefix) => bucket.arnForObjects(`${prefix}/*`)),
        }),
        new iam.PolicyStatement({
          actions: ['s3:ListBucket'],
          resources: [bucket.bucketArn],
          conditions: {
            StringLike: {
              's3:prefix': [
                'ready/*',
                'failed/*',
                'raw/*',
                'runs/*',
                'status/*',
                'quarantine/*',
                'invocation-failures/*',
                'work-failures/*',
              ],
            },
          },
        }),
        new iam.PolicyStatement({
          actions: ['s3:PutObject'],
          resources: [bucket.arnForObjects('approvals/*'), bucket.arnForObjects('ready/*')],
        }),
        new iam.PolicyStatement({
          actions: ['lambda:InvokeFunction'],
          resources: [reconcile.functionArn],
        }),
      ],
    });
    new cdk.CfnOutput(this, 'RecoveryOperatorPolicyArn', { value: operator.managedPolicyArn });
    for (const [name, fn] of [
      ['Fetch', fetch],
      ['Reconcile', reconcile],
    ] as const) {
      new cdk.CfnOutput(this, `${name}FunctionName`, { value: fn.functionName });
    }
  }
}
