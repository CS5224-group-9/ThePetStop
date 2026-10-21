#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { ApiStack } from '../lib/api-stack';
import { AuthStack } from '../lib/auth-stack';
import { DataStack } from '../lib/data-stack';
import { NetworkStack } from '../lib/network-stack';
import { StorageStack } from '../lib/storage-stack';

const app = new cdk.App();
const env = { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'ap-southeast-1' };
const prefix = 'PetStop-Dev';

const network = new NetworkStack(app, `${prefix}-Network`, { env });
const data = new DataStack(app, `${prefix}-Data`, {
  env,
  network,
  // Holds the database; turn off in the console before destroying after submission
  terminationProtection: true,
});
const storage = new StorageStack(app, `${prefix}-Storage`, { env });
const auth = new AuthStack(app, `${prefix}-Auth`, { env, frontendUrl: storage.frontendUrl });
new ApiStack(app, `${prefix}-Api`, { env, network, data, auth, storage });

cdk.Tags.of(app).add('Project', 'PetStop');
