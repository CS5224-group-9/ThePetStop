import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

/**
 * VPC with isolated subnets only: no NAT gateway, so nothing inside reaches the
 * internet. AWS services are reached through VPC endpoints (docs/architecture.md).
 */
export class NetworkStack extends cdk.Stack {
  readonly vpc: ec2.Vpc;
  /** For Lambdas that use the database. */
  readonly appSecurityGroup: ec2.SecurityGroup;
  readonly databaseSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      // RDS needs subnets in two AZs
      availabilityZones: ['ap-southeast-1a', 'ap-southeast-1b'],
      natGateways: 0,
      subnetConfiguration: [
        { name: 'isolated', subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });

    // Free; for pet files and the facility sync JSON
    this.vpc.addGatewayEndpoint('S3', { service: ec2.GatewayVpcEndpointAwsService.S3 });

    // Charged per AZ, so only one; Lambdas in the other AZ reach it across AZs
    this.vpc.addInterfaceEndpoint('SecretsManager', {
      service: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
      subnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
        availabilityZones: [this.vpc.availabilityZones[0]],
      },
    });

    this.appSecurityGroup = new ec2.SecurityGroup(this, 'AppSecurityGroup', {
      vpc: this.vpc,
      description: 'Lambdas that use the database',
    });
    this.databaseSecurityGroup = new ec2.SecurityGroup(this, 'DatabaseSecurityGroup', {
      vpc: this.vpc,
      description: 'RDS PostgreSQL',
      allowAllOutbound: false,
    });
    this.databaseSecurityGroup.addIngressRule(
      this.appSecurityGroup,
      ec2.Port.tcp(5432),
      'PostgreSQL from app Lambdas',
    );
  }
}
