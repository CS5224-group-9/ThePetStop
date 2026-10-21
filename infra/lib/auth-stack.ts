import * as cdk from 'aws-cdk-lib/core';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as cr from 'aws-cdk-lib/custom-resources';
import { Construct } from 'constructs';
import { twoWeekLogGroup } from './log-group';

const LOCAL_FRONTEND = 'http://localhost:3000';

// The frontend sends access tokens, which carry no email by default
const ADD_EMAIL_TO_ACCESS_TOKEN = `
def handler(event, context):
    email = event["request"]["userAttributes"].get("email")
    if email:
        event["response"]["claimsAndScopeOverrideDetails"] = {
            "accessTokenGeneration": {"claimsToAddOrOverride": {"email": email}}
        }
    return event
`;

// Runs outside the VPC at deploy time, because the API Lambda cannot download keys
const FETCH_JWKS = `
import urllib.request

def handler(event, context):
    url = event["ResourceProperties"]["JwksUrl"]
    if event["RequestType"] == "Delete":
        return {"PhysicalResourceId": url}
    with urllib.request.urlopen(url, timeout=10) as response:
        return {"PhysicalResourceId": url, "Data": {"Jwks": response.read().decode()}}
`;

export interface AuthStackProps extends cdk.StackProps {
  /** CloudFront URL, registered as a sign-in callback alongside localhost */
  frontendUrl: string;
}

/** Cognito user pool with managed login, the SPA client and the owner and merchant groups. */
export class AuthStack extends cdk.Stack {
  readonly userPool: cognito.UserPool;
  readonly client: cognito.UserPoolClient;
  readonly issuer: string;
  /** The pool's public signing keys as JSON, passed to Django */
  readonly jwks: string;

  constructor(scope: Construct, id: string, props: AuthStackProps) {
    super(scope, id, props);

    this.userPool = new cognito.UserPool(this, 'UserPool', {
      // Needed for the access-token customisation below
      featurePlan: cognito.FeaturePlan.ESSENTIALS,
      selfSignUpEnabled: true,
      signInAliases: { email: true },
      autoVerify: { email: true },
      standardAttributes: { email: { required: true, mutable: true } },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
    });

    this.userPool.addTrigger(
      cognito.UserPoolOperation.PRE_TOKEN_GENERATION_CONFIG,
      new lambda.Function(this, 'PreTokenGeneration', {
        runtime: lambda.Runtime.PYTHON_3_13,
        handler: 'index.handler',
        code: lambda.Code.fromInline(ADD_EMAIL_TO_ACCESS_TOKEN),
        logGroup: twoWeekLogGroup(this, 'PreTokenGenerationLogs'),
      }),
      cognito.LambdaVersion.V2_0,
    );

    const domain = this.userPool.addDomain('Domain', {
      cognitoDomain: { domainPrefix: `petstop-dev-${this.account}` },
    });

    this.client = this.userPool.addClient('WebClient', {
      // A public browser client using authorization code + PKCE
      generateSecret: false,
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
        callbackUrls: [`${props.frontendUrl}/auth/callback/`, `${LOCAL_FRONTEND}/auth/callback/`],
        logoutUrls: [`${props.frontendUrl}/`, `${LOCAL_FRONTEND}/`],
      },
      supportedIdentityProviders: [cognito.UserPoolClientIdentityProvider.COGNITO],
      preventUserExistenceErrors: true,
    });

    // Everyone signed in is treated as an owner; add merchant staff to "merchant" by hand
    this.userPool.addGroup('OwnerGroup', { groupName: 'owner', description: 'Pet owners' });
    this.userPool.addGroup('MerchantGroup', {
      groupName: 'merchant',
      description: 'Merchant staff',
    });

    this.issuer = `https://cognito-idp.${this.region}.amazonaws.com/${this.userPool.userPoolId}`;

    const fetchJwks = new lambda.Function(this, 'FetchJwks', {
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'index.handler',
      code: lambda.Code.fromInline(FETCH_JWKS),
      timeout: cdk.Duration.seconds(30),
      logGroup: twoWeekLogGroup(this, 'FetchJwksLogs'),
    });
    const jwks = new cdk.CustomResource(this, 'Jwks', {
      serviceToken: new cr.Provider(this, 'JwksProvider', {
        onEventHandler: fetchJwks,
        logGroup: twoWeekLogGroup(this, 'JwksProviderLogs'),
      }).serviceToken,
      properties: { JwksUrl: `${this.issuer}/.well-known/jwks.json` },
    });
    this.jwks = jwks.getAttString('Jwks');

    new cdk.CfnOutput(this, 'CognitoIssuer', { value: this.issuer });
    new cdk.CfnOutput(this, 'CognitoClientId', { value: this.client.userPoolClientId });
    new cdk.CfnOutput(this, 'CognitoDomain', { value: domain.baseUrl() });
  }
}
