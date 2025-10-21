# IntelliMaint Infrastructure

This directory contains infrastructure as code (IaC) and DevOps configurations.

## Structure

- `docker-compose.yml` - Local development setup
- `nginx.conf` - Reverse proxy configuration
- `terraform/` - AWS infrastructure (ECS, RDS, S3, CloudFront)
- `grafana/` - Monitoring dashboards and Prometheus config
- `github/` - CI/CD workflows (build, test, deploy, lint)

## Getting Started

### Local Development
```bash
docker-compose up -d
```

### Deploy Infrastructure
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

## Monitoring

Access Grafana at http://localhost:3001 (admin/admin)
Access Prometheus at http://localhost:9090

