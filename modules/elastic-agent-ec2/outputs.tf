output "instance_id" {
  value = aws_instance.agent.id
}

output "instance_name" {
  value = var.name
}

output "private_ip" {
  value = aws_instance.agent.private_ip
}

output "public_ip" {
  value = aws_instance.agent.public_ip
}

output "security_group_id" {
  value = aws_security_group.agent.id
}
