# Prometheus configuration (can be deployed on ECS or EC2)

resource "aws_ecs_task_definition" "prometheus" {
  family                   = "${var.project_name}-prometheus"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"

  container_definitions = jsonencode([{
    name  = "prometheus"
    image = "prom/prometheus:latest"
    portMappings = [{
      containerPort = 9090
      protocol      = "tcp"
    }]
  }])
}

