# infra

AWS CDK app in TypeScript that defines ThePetStop's AWS resources in `ap-southeast-1`. Managed with Yarn. The target architecture is in [docs/architecture.md](../docs/architecture.md).

## Prerequisites

- Node.js and Yarn.
- AWS CLI 2.32.0 or later (`aws --version`).
- An IAM user in the team account, with MFA and the `SignInLocalDevelopmentAccess` managed policy attached (needed for `aws login`).

## Signing in to AWS

Use `aws login`, which gives short-term credentials that refresh automatically for up to 12 hours. Do not create long-term access keys.

```powershell
aws login --profile petstop
aws sts get-caller-identity --profile petstop
```

The second command should print your IAM user's ARN. Run `aws login --profile petstop` again when the session expires.

- If the browser shows **400 Bad Request** after you sign in, sign out of the AWS console in that browser (or use a private window) and retry. If it still fails, run `aws login --profile petstop --remote` and paste the code shown in the browser back into the terminal.
- CDK uses the `default` profile unless told otherwise, and reports "no credentials" if you forget. Set the profile once per terminal:

  ```powershell
  $env:AWS_PROFILE = "petstop"
  ```

  or add `--profile petstop` to each `cdk` command.

## Bootstrapping

Bootstrapping creates the `CDKToolkit` stack that CDK deploys through. It is needed **once per account and region** and has already been done for the team account, so skip it unless you are setting up a new account:

```powershell
yarn cdk bootstrap aws://<ACCOUNT_ID>/ap-southeast-1
```

`aws sts get-caller-identity` prints the account ID.

## Stacks

Defined in `bin/infra.ts`, one file each in `lib/`:

| Stack                 | Contains                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `PetStop-Dev-Network` | VPC with isolated subnets in two AZs and no NAT gateway; S3 gateway endpoint; Secrets Manager interface endpoint in one AZ; security groups for the app Lambdas and the database                                                                                                                                                                                         |
| `PetStop-Dev-Data`    | RDS PostgreSQL 16 `db.t4g.micro` with a generated credentials secret, 7-day backups and deletion protection; the Django secret key. Termination protection is on.                                                                                                                                                                                                        |
| `PetStop-Dev-Storage` | S3 buckets `Web`, `ProductImages` (served at `/product-images/*`) and private, versioned `PetFiles` (a lifecycle rule expires noncurrent versions after 7 days, removes expired delete markers and aborts incomplete multipart uploads after 1 day); CloudFront with OAC and a function that maps `/x/` to `/x/index.html`                                               |
| `PetStop-Dev-Auth`    | Cognito user pool with managed login, the public SPA client (code + PKCE), groups `owner` and `merchant`, a trigger that adds `email` to access tokens, and a deploy-time fetch of the pool's public keys                                                                                                                                                                |
| `PetStop-Dev-Api`     | The Django image as two Lambdas in the VPC (`ApiFunction` for requests, `ManageFunction` for migrations); both get `PET_FILES_BUCKET`, and only `ApiFunction` may put, get and delete `PetFiles` objects under `pets/*` (object ARNs only, no list access); HTTP API whose catch-all route requires a Cognito JWT, with public `GET` routes for health and the catalogue |

All Lambda logs keep 14 days. Expect roughly US$25–35 a month, mostly RDS and the Secrets Manager endpoint; check the Budgets alarm after the first week.

## Commands

From `infra/`, with `AWS_PROFILE` set:

- `yarn install`: install dependencies.
- `yarn build`: type-check the project.
- `yarn test`: check the synthesized templates.
- `yarn format` (or `yarn format:check`): format with Prettier.
- `yarn cdk synth`: print the CloudFormation templates.
- `yarn cdk diff`: compare with what is deployed. Run it before every deploy; a renamed construct replaces the resource.
- `yarn cdk deploy --all`: deploy every stack. Docker Desktop must be running, because CDK builds `backend/Dockerfile`.

## Deploying from GitHub

`.github/workflows/deploy.yml` deploys `main` whenever a push changes `backend/`, `frontend/`, `infra/` or the workflow itself. It can also be started by hand from the Actions tab, but only on `main`. In order, it:

1. runs `cdk deploy --all`, which builds and pushes the backend image;
2. runs `migrate` through `ManageFunction`, and fails if the command raises;
3. checks that `<ApiBaseUrl>health/` answers;
4. builds the frontend in API mode from the stack outputs; no frontend settings are stored in GitHub;
5. uploads it to the web bucket and invalidates CloudFront.

It signs in to AWS through GitHub OIDC with the role in the `AWS_ROLE_ARN` repository secret, `github-actions-petapp-prod`. That role trusts only `refs/heads/main`. To deploy, it needs permission to assume CDK's bootstrap roles. Add this once, as an administrator:

```powershell
Set-Content cdk-assume.json '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"sts:AssumeRole","Resource":"arn:aws:iam::<ACCOUNT_ID>:role/cdk-hnb659fds-*"}]}'
aws iam put-role-policy --role-name github-actions-petapp-prod --policy-name cdk-bootstrap-roles --policy-document file://cdk-assume.json
Remove-Item cdk-assume.json
```

`.github/workflows/infra-ci.yml` runs Prettier, `tsc` and the template tests on every pull request.

## Deploying by hand

The same steps from a laptop, for a first deploy or when the workflow is broken. `backend/.dockerignore` excludes `.local-storage` (the local storage backend's pet files), so a laptop deploy never ships local test files. From `infra/`:

1. Deploy, then note the outputs it prints (`ApiBaseUrl`, `ManageFunctionName`, `FrontendUrl`, `WebBucketName`, `DistributionId`, `CognitoIssuer`, `CognitoClientId`, `CognitoDomain`):

   ```powershell
   yarn cdk deploy --all
   ```

2. Run the migrations:

   ```powershell
   Set-Content payload.json '{"command": "migrate"}'
   aws lambda invoke --function-name <ManageFunctionName> --payload fileb://payload.json migrate-result.json
   Get-Content migrate-result.json
   Remove-Item payload.json, migrate-result.json
   ```

3. Check the API: `<ApiBaseUrl>health/` should return `{"status":"ok"}`, and `<ApiBaseUrl>me/` should return 401.

4. Build the frontend against the deployed services. In `frontend/.env.production.local`, set `NEXT_PUBLIC_DATA_SOURCE=api`, `NEXT_PUBLIC_API_BASE_URL=<ApiBaseUrl>`, `NEXT_PUBLIC_COGNITO_ISSUER`, `NEXT_PUBLIC_COGNITO_CLIENT_ID`, `NEXT_PUBLIC_COGNITO_DOMAIN`, `NEXT_PUBLIC_COGNITO_REDIRECT_URI=<FrontendUrl>/auth/callback/` and `NEXT_PUBLIC_COGNITO_LOGOUT_URI=<FrontendUrl>/`. Then, from `frontend/`:

   ```powershell
   yarn build
   aws s3 sync out/ s3://<WebBucketName> --delete
   aws cloudfront create-invalidation --distribution-id <DistributionId> --paths "/*"
   ```

5. M0 check: open `<FrontendUrl>`, sign up, sign in, and confirm the app loads your profile from `/me/`.

To give someone merchant access, add their user to the `merchant` group in the Cognito console.
