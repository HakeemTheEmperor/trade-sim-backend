#!/bin/bash
#
# ____          __  __  _____ 
# |  _ \   /\   |  \/  |/ ____|     repo:     https://github.com/opeoniye
# | |_) | /  \  | \  / | (___       porfolio: https://opeoniye.vercel.app/
# |  _ < / /\ \ | |\/| |\___ \      credit:   http://patorjk.com/software/taag/
# | |_) / ____ \| |  | |____) |
# |____/_/    \_\_|  |_|_____/ 
#                             
#
# Based on https://gist.github.com/2206527

# load .env
# source ./.env

# colours
RED='\033[31m'
RED_BOLD='\033[1;31m'
BLUE='\033[34m'
BLUE_BOLD='\033[1;34m'
GREEN='\033[32m'
GREEN_BOLD='\033[1;32m'
YELLOW='\033[33m'
YELLOW_BOLD='\033[1;33m'
RESET='\033[0m'

# reactjs things
reactjs() {
  echo -e "${GREEN}Starting ReactJS app in $NODE_ENV${RESET}"
  npm start
}

# nextjs things
nextjs() {
  echo -e "${GREEN}Starting NextJS app in $NODE_ENV${RESET}"
  npm start
}

# nodejs things
nodejs() {
  echo -e "${GREEN}Starting Nodejs app in $NODE_ENV${RESET}"
  dumb-init pm2-runtime ecosystem.config.js
}

# laravel things
laravel() {
  echo -e "${GREEN}Running laravel commands${RESET}"
  cd /var/www
  php artisan cache:clear
  php artisan optimize
  # php artisan migrate:fresh --seed
  /usr/bin/supervisord -c /etc/supervisord.conf
}

# supervisor things
php() {
  echo -e "${GREEN}Starting all services with supervisord${RESET}"
  /usr/bin/supervisord -c /etc/supervisord.conf
}

# run
if [ "$DL_APP_STACK" == "reactjs" ]; then
  reactjs
elif [ "$DL_APP_STACK" == "nextjs" ]; then
  nextjs
elif [ "$DL_APP_STACK" == "nodejs" ]; then
  nodejs
elif [ "$DL_APP_STACK" == "laravel" ]; then
  laravel
elif [ "$DL_APP_STACK" == "php" ]; then
  php
else
  echo -e "App stack not found. Try and set in your envfile"
  exit 0
fi
