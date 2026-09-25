data "aws_ami" "debian" {
  most_recent = true
  owners      = ["136693071363"] # Debian

  filter {
    name   = "name"
    values = ["debian-12-amd64-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

data "aws_vpc" "default" {
  count   = var.vpc_id == "" || var.subnet_id == "" ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.subnet_id == "" ? 1 : 0

  filter {
    name = "vpc-id"
    values = [
      var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
    ]
  }
}

locals {
  vpc_id    = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_id = var.subnet_id != "" ? var.subnet_id : sort(data.aws_subnets.default[0].ids)[0]
  tags = merge(
    {
      Name      = var.name
      ManagedBy = "terraform"
      Role      = "elastic-agent"
    },
    var.company_tags,
  )
}

resource "aws_security_group" "agent" {
  name        = "${var.name}-sg"
  description = "Egress for Elastic Agent Fleet enrollment and log collection"
  vpc_id      = local.vpc_id
  tags        = local.tags

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "agent" {
  ami                         = data.aws_ami.debian.id
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.agent.id]
  associate_public_ip_address = var.associate_public_ip
  user_data_replace_on_change = true

  user_data = templatefile("${path.module}/templates/install_agent.sh.tftpl", {
    fleet_url        = var.fleet_url
    enrollment_token = var.enrollment_token
    agent_version    = var.agent_version
  })

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
    tags        = local.tags
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = local.tags
}
