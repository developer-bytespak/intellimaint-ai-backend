# Grafana deployment configuration

resource "aws_ecs_task_definition" "grafana" {
  family                   = "${var.project_name}-grafana"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"

  container_definitions = jsonencode([{
    name  = "grafana"
    image = "grafana/grafana:latest"
    portMappings = [{
      containerPort = 3001
      protocol      = "tcp"
    }]
    environment = [
      {
        name  = "GF_SECURITY_ADMIN_PASSWORD"
        value = "admin"
      }
    ]
  }])
}

