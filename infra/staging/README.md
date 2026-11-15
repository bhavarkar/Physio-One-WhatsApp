# Staging IaC (Task 14) — validate only, DO NOT apply without approval

```bash
cd infra/staging
terraform init -backend-config="bucket=<STATE_BUCKET>"   # bucket created manually once
TF_VAR_project_id=<STAGING_PROJECT> TF_VAR_api_image=<IMAGE> TF_VAR_frontend_image=<IMAGE> terraform plan
terraform fmt -check && terraform validate
```

- No project IDs, secrets, or service-account keys are committed. Secret *values* are added with `gcloud secrets versions add` out-of-band.
- Cost estimate ≈ USD 15–35/month (see `DEPLOYMENT.md` §8). Set a billing budget alert before `apply`.
- Cleanup: `terraform destroy` (staging only) or delete the staging project.
- Rollback: redeploy previous image tags; IaC state is staging-scoped.
