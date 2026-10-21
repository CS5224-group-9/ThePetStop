import * as cdk from 'aws-cdk-lib/core';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

const LOCAL_FRONTEND = 'http://localhost:3000';

// S3 behind CloudFront OAC does not serve sub-folder index files, so map
// /pets/detail/ (or /pets/detail) to /pets/detail/index.html. The query string is kept.
const INDEX_REWRITE = `
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith('/')) {
    request.uri = uri + 'index.html';
  } else if (uri.split('/').pop().indexOf('.') === -1) {
    request.uri = uri + '/index.html';
  }
  return request;
}`;

/** S3 buckets and the CloudFront distribution that serves the frontend. */
export class StorageStack extends cdk.Stack {
  readonly webBucket: s3.Bucket;
  readonly productImagesBucket: s3.Bucket;
  readonly petFilesBucket: s3.Bucket;
  readonly distribution: cloudfront.Distribution;
  /** e.g. https://d111111abcdef8.cloudfront.net, with no trailing slash */
  readonly frontendUrl: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const privateBucket: s3.BucketProps = {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
    };

    // The Next.js static export; rebuilt on every deploy, so safe to delete
    this.webBucket = new s3.Bucket(this, 'Web', {
      ...privateBucket,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Public catalogue images, served at /product-images/*. Object keys must start
    // with product-images/.
    this.productImagesBucket = new s3.Bucket(this, 'ProductImages', privateBucket);

    const indexRewrite = new cloudfront.Function(this, 'IndexRewrite', {
      runtime: cloudfront.FunctionRuntime.JS_2_0,
      code: cloudfront.FunctionCode.fromInline(INDEX_REWRITE),
    });

    this.distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultRootObject: 'index.html',
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(this.webBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        functionAssociations: [
          { function: indexRewrite, eventType: cloudfront.FunctionEventType.VIEWER_REQUEST },
        ],
      },
      additionalBehaviors: {
        '/product-images/*': {
          origin: origins.S3BucketOrigin.withOriginAccessControl(this.productImagesBucket),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          responseHeadersPolicy: cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
        },
      },
      // Without ListBucket, S3 answers a missing object with 403
      errorResponses: [403, 404].map((httpStatus) => ({
        httpStatus,
        responseHttpStatus: 404,
        responsePagePath: '/404.html',
        ttl: cdk.Duration.minutes(1),
      })),
      // Includes edge locations in Asia
      priceClass: cloudfront.PriceClass.PRICE_CLASS_200,
    });
    this.frontendUrl = `https://${this.distribution.distributionDomainName}`;

    // Pet photos and vet reports. Private; the API hands out presigned URLs and the
    // browser uploads directly.
    this.petFilesBucket = new s3.Bucket(this, 'PetFiles', {
      ...privateBucket,
      versioned: true,
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.PUT],
          allowedOrigins: [this.frontendUrl, LOCAL_FRONTEND],
          allowedHeaders: ['content-type'],
          maxAge: 3000,
        },
      ],
    });

    new cdk.CfnOutput(this, 'FrontendUrl', { value: this.frontendUrl });
    new cdk.CfnOutput(this, 'WebBucketName', { value: this.webBucket.bucketName });
    new cdk.CfnOutput(this, 'DistributionId', { value: this.distribution.distributionId });
  }
}
