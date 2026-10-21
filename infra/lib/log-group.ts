import * as cdk from 'aws-cdk-lib/core';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

/** A log group with the project's 14-day retention, deleted with its stack. */
export function twoWeekLogGroup(scope: Construct, id: string) {
  return new logs.LogGroup(scope, id, {
    retention: logs.RetentionDays.TWO_WEEKS,
    removalPolicy: cdk.RemovalPolicy.DESTROY,
  });
}
