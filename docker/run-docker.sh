#!/bin/bash

latest_tag=$(git describe --tags --abbrev=0)
module_name=doc-gather

docker run \
  -d -it \
  -e WORKER_NUM=2 \
  -p 8005:8005 \
  --name ${module_name} \
  ${module_name}:${latest_tag}
