import * as path from 'node:path';
import * as cdk from 'aws-cdk-lib/core';
import * as apigw from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpJwtAuthorizer } from 'aws-cdk-lib/aws-apigatewayv2-authorizers';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Construct } from 'constructs';
import { AuthStack } from './auth-stack';
import { DataStack } from './data-stack';
import { twoWeekLogGroup } from './log-group';
import { NetworkStack } from './network-stack';
import { StorageStack } from './storage-stack';

const LOCAL_FRONTEND = 'http://localhost:3000';

// Public in the API contract (docs/repository-structure.md). Every other route needs
// a Cognito token at the gateway, so a path that matches none of these fails closed.
// Django checks the token and permissions again either way.
// Django URLs end in "/". A route such as /api/v1/health does not match
// /api/v1/health/, but /api/v1/health/{proxy+} matches both it and anything below it.
const PUBLIC_GET_PREFIXES = ['health', 'facilities', 'categories', 'merchants', 'products'];

export interface ApiStackProps extends cdk.StackProps {
  network: NetworkStack;
  data: DataStack;
  auth: AuthStack;
  storage: StorageStack;
}

/** The Django API on Lambda behind an API Gateway HTTP API. */
export class ApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);
    const { network, data, auth, storage } = props;

    // CDK builds backend/Dockerfile and pushes it to the bootstrap ECR repository
    const image = (handler: string) =>
      lambda.DockerImageCode.fromImageAsset(path.join(__dirname, '../../backend'), {
        platform: Platform.LINUX_AMD64,
        cmd: [handler],
      });

    const api = new apigw.HttpApi(this, 'HttpApi', {
      corsPreflight: {
        allowOrigins: [storage.frontendUrl, LOCAL_FRONTEND],
        allowMethods: [apigw.CorsHttpMethod.ANY],
        allowHeaders: ['authorization', 'content-type', 'idempotency-key'],
        maxAge: cdk.Duration.hours(1),
      },
    });
    const apiHost = `${api.apiId}.execute-api.${this.region}.amazonaws.com`;

    const shared: Partial<lambda.DockerImageFunctionProps> = {
      architecture: lambda.Architecture.X86_64,
      memorySize: 1024,
      vpc: network.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED },
      securityGroups: [network.appSecurityGroup],
      environment: {
        DJANGO_SECRET_KEY_ARN: data.djangoSecretKey.secretArn,
        DB_SECRET_ARN: data.database.secret!.secretArn,
        DJANGO_ALLOWED_HOSTS: apiHost,
        DJANGO_CORS_ALLOWED_ORIGINS: storage.frontendUrl,
        COGNITO_ISSUER: auth.issuer,
        COGNITO_CLIENT_ID: auth.client.userPoolClientId,
        COGNITO_JWKS: auth.jwks,
        // Both functions get it so settings load the same way for migrate and check.
        // The region comes from AWS_REGION, which Lambda sets.
        PET_FILES_BUCKET: storage.petFilesBucket.bucketName,
      },
    };

    const apiFunction = new lambda.DockerImageFunction(this, 'ApiFunction', {
      ...shared,
      code: image('config.lambda_handler.api'),
      // API Gateway gives up after 30 seconds
      timeout: cdk.Duration.seconds(29),
      logGroup: twoWeekLogGroup(this, 'ApiFunctionLogs'),
    });

    // Presigned PUT/GET and the upload completion check (HeadObject needs GetObject).
    // Object ARNs only: no ListBucket, so the API cannot enumerate other pets' files.
    // Not grantReadWrite, which adds s3:List* and s3:GetBucket*. ManageFunction gets
    // no S3 access.
    apiFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['s3:PutObject', 's3:GetObject', 's3:DeleteObject'],
        resources: [storage.petFilesBucket.arnForObjects('pets/*')],
      }),
    );

    // Invoked by the deploy workflow with {"command": "migrate"}
    const manageFunction = new lambda.DockerImageFunction(this, 'ManageFunction', {
      ...shared,
      code: image('config.lambda_handler.manage'),
      timeout: cdk.Duration.minutes(5),
      logGroup: twoWeekLogGroup(this, 'ManageFunctionLogs'),
    });

    for (const fn of [apiFunction, manageFunction]) {
      data.djangoSecretKey.grantRead(fn);
      data.database.secret!.grantRead(fn);
    }

    const integration = new HttpLambdaIntegration('Django', apiFunction);
    const authorizer = new HttpJwtAuthorizer('Cognito', auth.issuer, {
      // Cognito access tokens carry the app client in client_id, which this checks
      jwtAudience: [auth.client.userPoolClientId],
    });

    // Catch-all: protected
    new apigw.HttpRoute(this, 'DefaultRoute', {
      httpApi: api,
      routeKey: apigw.HttpRouteKey.DEFAULT,
      integration,
      authorizer,
    });
    for (const prefix of PUBLIC_GET_PREFIXES) {
      api.addRoutes({
        path: `/api/v1/${prefix}/{proxy+}`,
        methods: [apigw.HttpMethod.GET],
        integration,
      });
    }
    // Browsers send CORS preflights without a token. Without this route they hit the
    // catch-all and get 401; with it, API Gateway answers them from corsPreflight.
    api.addRoutes({ path: '/{proxy+}', methods: [apigw.HttpMethod.OPTIONS], integration });

    new cdk.CfnOutput(this, 'ApiBaseUrl', { value: `https://${apiHost}/api/v1/` });
    new cdk.CfnOutput(this, 'ManageFunctionName', { value: manageFunction.functionName });
  }
}
