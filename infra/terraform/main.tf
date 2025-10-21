terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Backend configuration for state management
terraform {
  backend "s3" {
    bucket = "intellimaint-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
  }
}

