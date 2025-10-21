# RDS PostgreSQL Instance
resource "aws_db_instance" "postgres" {
  identifier           = "${var.project_name}-postgres"
  engine               = "postgres"
  engine_version       = "15"
  instance_class       = var.db_instance_class
  allocated_storage    = 20
  storage_type         = "gp3"
  
  db_name  = "intellimaint"
  username = "admin"
  password = "changeme"  # Use secrets manager in production
  
  skip_final_snapshot = true
  publicly_accessible = false
  
  tags = {
    Name        = "${var.project_name}-postgres"
    Environment = var.environment
  }
}

