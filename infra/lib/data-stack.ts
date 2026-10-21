import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';
import { NetworkStack } from './network-stack';

export interface DataStackProps extends cdk.StackProps {
  network: NetworkStack;
}

/** Stateful resources: the database and the Django secret key. */
export class DataStack extends cdk.Stack {
  readonly database: rds.DatabaseInstance;
  readonly djangoSecretKey: secretsmanager.Secret;

  constructor(scope: Construct, id: string, props: DataStackProps) {
    super(scope, id, props);

    this.database = new rds.DatabaseInstance(this, 'Database', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
      vpc: props.network.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [props.network.databaseSecurityGroup],
      // Username, password, host, port and dbname, read by Django at start-up
      credentials: rds.Credentials.fromGeneratedSecret('petstop'),
      databaseName: 'petstop',
      allocatedStorage: 20,
      storageType: rds.StorageType.GP3,
      storageEncrypted: true,
      multiAz: false,
      publiclyAccessible: false,
      backupRetention: cdk.Duration.days(7),
      deletionProtection: true,
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
    });

    this.djangoSecretKey = new secretsmanager.Secret(this, 'DjangoSecretKey', {
      description: 'Django SECRET_KEY for the API',
      generateSecretString: { passwordLength: 64, excludePunctuation: true },
    });
  }
}
