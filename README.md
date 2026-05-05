# kubernetes-portfolio
# Kubernetes Portfolio

A collection of production-grade Kubernetes configurations built during hands-on training.

## Projects

### Blue-Green Deployment with NGINX
Demonstrates zero-downtime deployments using two live environments.
- Tools: Kubernetes, kubectl, NGINX
- Concepts: Deployments, Services, Labels, Selectors
- File: deployments/nginx-blue-green.yaml

How to run:
  kubectl apply -f deployments/nginx-blue-green.yaml
  kubectl get svc nginx-service

### Coming soon
- Persistent Volumes and StatefulSets
- Helm chart deployments
- CI/CD with GitHub Actions
