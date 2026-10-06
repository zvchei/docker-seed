
# Installed into the image, so `pi update` cannot persist; rebuild to upgrade.
RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent
