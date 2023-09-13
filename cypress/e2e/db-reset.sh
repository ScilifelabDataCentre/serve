#!/bin/bash

# Delete all data from database
# And restart the docker container
# There are some unique setup instructions that Nikita could not replicate here

docker exec studio bash -c "python manage.py flush --no-input"
docker restart studio

while true; do
  # Run the curl command and capture both stdout and stderr
  output=$(curl "studio.127.0.0.1.nip.io:8080/" 2>&1)
  echo "$output"

  # Check if the output is empty or contains the "Empty reply from server" message
  if [[ -z "$output" || "$output" == *"Empty reply from server"* ]]; then
    echo "Failed: Empty reply from server or no output"
    sleep 1 # Wait for 1 second before retrying
  else
    echo "Success: $output"
    break
  fi
done
