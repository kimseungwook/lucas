# Build Images

This repo ships three images.

## Agent (Slack)

```bash
podman build --platform=linux/amd64 -f Dockerfile.agent -t your-registry/lucas-agent:tag .
podman push your-registry/lucas-agent:tag
```

## Dashboard

```bash
docker buildx build --platform linux/amd64,linux/arm64 -f Dockerfile.dashboard -t your-registry/lucas-dashboard:tag --push .
```

Current Harbor example:

```bash
docker buildx build --platform linux/amd64,linux/arm64 -f Dockerfile.dashboard -t gdhb.goyoai.com/lukas/lucas-dashboard:postgres --push .
```

## Agent (CronJob)

```bash
podman build --platform=linux/amd64 -f Dockerfile.lucas -t your-registry/lucas:tag .
podman push your-registry/lucas:tag
```

Update the image tags in `k8s/` after pushing.
