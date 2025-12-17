variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "eu-central-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "key_name" {
  description = "Name of the SSH key pair"
  type        = string
  default     = "uptime-monitor-key"
}

variable "public_key_path" {
  description = "Path to the public SSH key file"
  type        = string
  default     = "./ssh-keys/uptime_key.pub"
}