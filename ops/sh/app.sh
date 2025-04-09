#!/bin/bash

# add envfile to shell
if [ "$(hostname)" == "bams" ] || [ "$(hostname)" == "dles-vm1" ] || [ "$(hostname)" == "DCLM-DLES-1" ]; then
  dotenv='./app/.env'
  
  if [ ! -f "$dotenv" ]; then
    echo ".env file not found!"
    exit 1
  fi
  
  . "$dotenv"
fi

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

#1 create nginx config
function nginx_config {
  export DL_APP_NAME DL_APP_NGX_DOCROOT DL_APP_NGX_SERVER_NAME DL_APP_NGX_INDEX
  # Generate config 
  envsubst '${DL_APP_NAME},${DL_APP_NGX_DOCROOT},${DL_APP_NGX_SERVER_NAME},${DL_APP_NGX_INDEX}' < ./ops/nginx/app.template > ./ops/nginx/app.conf
}

#2 function to check which git branch
function git_branch {
  # Get the current Git branch
  branch=$(git rev-parse --abbrev-ref HEAD)

  # Check if branch is release/dev or release/prod
  if [[ $branch != "release/ec2-dev" ]] && [[ $branch != "release/ec2-prod" ]] && [[ $branch != "release/k8s-dev" ]] && [[ $branch != "release/dev" ]] && [[ $branch != "release/prev" ]] && [[ $branch != "release/prod" ]] && [[ $branch != "release/k8s-prod" ]]; then
    # Prompt the user to select a branch  
    echo -e "Current branch is ${RED}$branch.${RESET} You can only deploy on ${GREEN}release/ec2-dev${RESET}, ${GREEN}release/ec2-prod${RESET}, ${GREEN}release/k8s-dev${RESET}, ${GREEN}release/dev${RESET}, ${GREEN}release/k8s-dev${RESET} or ${GREEN}release/k8s-prod${RESET}"
    echo -e "Please select branch:"
    echo -e "1) ${YELLOW}release/ec2-dev${RESET}" 
    echo -e "2) ${YELLOW}release/ec2-prod${RESET}"
    echo -e "3) ${YELLOW}release/k8s-dev${RESET}"
    echo -e "4) ${YELLOW}release/dev${RESET}"
    echo -e "5) ${YELLOW}release/prev${RESET}"
    echo -e "6) ${YELLOW}release/k8s-prod${RESET}"
    echo -e "7) ${YELLOW}release/prod${RESET}"
    read -p "Enter choice: " choice

    # Switch based on choice
    case $choice in
      1) 
        echo -e "Switching to ${GREEN}release/ec2-dev${RESET} branch"
        git switch release/ec2-dev
        if [ $? -eq 0 ]; then
          :
        else
          echo -e "Could not switch to ${RED}release/ec2-dev${RESET} branch\n"
          exit 1
        fi
        ;;
      2)
        echo "Switching to ${GREEN}release/ec2-prod${RESET} branch" 
        git switch release/ec2-prod
        if [ $? -eq 0 ]; then
          :
        else
          echo -e "Could not switch to ${RED}release/ec2-prod${RESET} branch\n"
          exit 1
        fi
        ;;
      3)
        echo "Switching to ${GREEN}release/k8s-dev${RESET} branch" 
        git switch release/k8s-dev
        if [ $? -eq 0 ]; then
          :
        else
          echo -e "Could not switch to ${RED}release/k8s-dev${RESET} branch\n"
          exit 1
        fi
        ;;
      4)
        echo "Switching to ${GREEN}release/dev${RESET} branch" 
        git switch release/dev
        if [ $? -eq 0 ]; then
          :
        else
          echo -e "Could not switch to ${RED}release/dev${RESET} branch\n"
          exit 1
        fi
        ;;
      5)
        echo "Switching to ${GREEN}release/prev${RESET} branch" 
        git switch release/prev
        if [ $? -eq 0 ]; then
          :
        else
          echo -e "Could not switch to ${RED}release/prev${RESET} branch\n"
          exit 1
        fi
        ;;
      6)
        echo "Switching to ${GREEN}release/k8s-prod${RESET} branch" 
        git switch release/k8s-prod
        if [ $? -eq 0 ]; then
          :
        else
          echo -e "Could not switch to ${RED}release/k8s-prod${RESET} branch\n"
          exit 1
        fi
        ;;
      7)
        echo "Switching to ${GREEN}release/prod${RESET} branch" 
        git switch release/prod
        if [ $? -eq 0 ]; then
          :
        else
          echo -e "Could not switch to ${RED}release/prod${RESET} branch\n"
          exit 1
        fi
        ;;
      *)
        echo "Invalid choice" >&2
        exit 1
        ;;
    esac
  else 
    echo -e "Git Repo: You're on ${GREEN}$branch${RESET} branch"
  fi
}

#3 function to check if there are uncommitted changes in repo
function commit_status {
  # Check if the current directory is a Git repository
  if [ -d .git ] || git rev-parse --git-dir > /dev/null 2>&1; then
    :
  else
    echo "This is not a Git repository."
    exit 1
  fi

  # Check if the working tree is clean
  if [ -z "$(git status --porcelain)" ]; then
    echo -e "Repo Status: ${GREEN}Working tree is clean.${RESET}\n"
  else
    # echo -e "${RED}There are uncommitted files.${RESET} Type ${YELLOW}y|Y|yes${RESET} to fix."
    git_commit
  fi
}

#---------------------------------------#
# init                                  #
#---------------------------------------#
#4 function to create a git repo locally
function git_repo_create {
	read -p $'\nDo you want to create a git repo? (yes|no): ' repo_init
	case "$repo_init" in
		yes|Y|y)
			if [ -d .git ]; then
				echo -e "${RED}Current directory already initialised ${RESET}\n"
			else
				echo -e "${GREEN}Please enter initial commit message: ${RESET}\n"
				read -r commitMsg
				git init && git add . && git commit -m "$commitMsg"

        # Initialize Git repo
        git init
        git branch -M develop

        # Develop branch
        echo "Creating files in develop branch"
        mkdir src
        touch README.md
        echo "Please delete before first commit. Thank you!" >> src/info.txt
        git add .
        read -p "Enter develop commit message: " cm_develop
        git commit -m "$cm_develop"

        # Main branch
        git branch main
        git checkout main
        echo "Creating files in main branch" 
        mkdir docs
        touch dclm-app .gitignore Makefile
        git add .
        read -p "Enter main commit message: " cm_main  
        git commit -m "$cm_main"

        # bams branch 
        git checkout -b bams
        echo "Creating files in bams branch"
        mkdir -p .github/workflows docs ops
        mkdir -p ops/{dkr,mk,nginx,php,sh}
        touch ops/.gitignore ops/Makefile
        touch .github/deploy.yml
        git add .
        read -p "Enter commit message: " cm_bamsdev
        git commit -m "$cm_bamsdev"

        # release/ec2-dev branch
        git checkout -b release/ec2-dev 
        echo "Committing in release/ec2-dev branch"
        git add .
        read -p "Enter commit message: " cm_ec2dev
        git commit -m "$cm_ec2dev"

        # release/ec2-prod branch
        git checkout -b release/ec2-prod
        echo "Committing in release/ec2-prod branch" 
        git add .
        read -p "Enter commit message: " cm_ec2prod
        git commit -m "$cm_ec2prod"

        # release/k8s-dev branch
        git checkout -b release/k8s-dev
        echo "Committing in release/k8s-dev branch" 
        git add .
        read -p "Enter commit message: " cm_k8sdev
        git commit -m "$cm_k8sdev"

        # release/dev branch
        git checkout -b release/dev
        echo "Committing in release/dev branch" 
        git add .
        read -p "Enter commit message: " cm_dev
        git commit -m "$cm_dev"

        # release/prev branch
        git checkout -b release/prev
        echo "Committing in release/prev branch" 
        git add .
        read -p "Enter commit message: " cm_prev
        git commit -m "$cm_prev"

        # release/k8s-prod branch
        git checkout -b release/k8s-prod
        echo "Committing in release/k8s-prod branch" 
        git add .
        read -p "Enter commit message: " cm_k8sprod
        git commit -m "$cm_k8sprod"

        # release/prod branch
        git checkout -b release/prod
        echo "Committing in release/prod branch" 
        git add .
        read -p "Enter commit message: " cm_prod
        git commit -m "$cm_prod"

			fi
			;;
		no|N|n)
			echo -e "${GREEN}Alright. Thank you...${RESET}"
			;;
		*) \
			echo -e "${GREEN}No choice. Exiting script...${RESET}"
			;;
	esac
}

#5 function to create a repository on GitHub
function gh_repo_create {
	read -p $'\nDo you want to create a github repo? (yes|no): ' repo_name
	case "$repo_name" in
		yes|Y|y)
			read -p "Enter GitHub username: " ghUser
			read -p "Enter GitHub repo name: " ghName
      gh="$ghUser/$ghName"
			result="$(gh_repo_check $gh)"
			if [ $result -eq 200 ]; then
				echo -e "${RED}GitHub repo exists. I stop here. ${RESET}\n"
			else
				echo -e "\nWhich type of repository are you creating?:"
				echo "1. Private repo"
				echo "2. Public repo"
				read -p "Enter a number to select your choice: " repoType
				if [ $repoType -eq 1 ]; then
					REPO=private
				elif [ $repoType -eq 2 ]; then
					REPO=public
				else
					echo "Invalid choice"
					exit 0
				fi
				gh repo create ${ghUser}/${ghName} --$REPO --source=. --remote=origin
			fi
			;;
		no|N|n)
			echo -e "${GREEN}Okay, thank you...${RESET}"
			;;
		*)
			echo -e "${GREEN} No choice. Exiting script...${RESET}"
			;;
	esac
}

#---------------------------------------#
# app                                   #
#---------------------------------------#
#6 function to commit git repository
function git_commit {
  # function to commit repo with untracked files
  git_commit_new() {
    read -p $'\nDo you want to commit repo files? (yes|no): ' git_commit
    case "$git_commit" in
      yes|Y|y)
        echo -e "\n${RED}Untracked files found and listed below: ${RESET}"
        git status -s
        echo -e $'\n'"${GREEN}Please enter commit message${RESET}: \c"
        read msg
        git add -A
        git commit -m "$msg"
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        ;;
    esac
  }

  # function to commit repo with modified files
  git_commit_old() {
    read -p $'\nDo you want to commit repo files? (yes|no): ' git_commit
    case "$git_commit" in
      yes|Y|y)
        echo -e "\n${RED}Modified files found and listed below: ${RESET}"
        git status -s
        echo -e $'\n'"${GREEN}Please enter commit message${RESET}: \c"
        read msg
        git commit -am "$msg"
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        ;;
    esac
  }

  if git status --porcelain | grep -q "^??"; then
    git_commit_new
  elif git status --porcelain | grep -qE '[^ADMR]'; then
    git_commit_old
  elif [ -z "$(git status --porcelain)" ]; then
    echo -e "${RED} Nothing to commit, thanks...${RESET}\n"
  else
    echo -e "${RED} Unknown status. Aborting...${RESET}\n"
    exit 1
  fi
}

#7 build docker image
function docker_build {
  # function to purge docker images
  function dkr_purge_image {
    local bypass_prompt=$1
    if [ -z "$bypass_prompt" ]; then
      read -p $'\nDo you want to purge images? (yes|no): ' dkr_purge
    else
      dkr_purge=$bypass_prompt
    fi

    case "$dkr_purge" in
      yes|y)
        if [ "$(docker images -qf "dangling=true")" ]; then
          echo -e "${RED}Removing dangling images...${RESET}"
          docker image prune -f
        else
          echo -e "${GREEN}No dangling images found.${RESET}"
        fi
        ;;
      no|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${RED}Invalid choice. Exiting script...${RESET}\n"
        return 1
        ;;
    esac

    if [ $? -eq 0 ]; then
      echo -e "${GREEN}Image purge process completed successfully.${RESET}"
      return 0
    else
      echo -e "${RED}Image purge process encountered errors.${RESET}"
      return 1
    fi
  }


  # function to delete docker image
  function dkr_rmi_image {
    local bypass_prompt=$1
    if [ -z "$bypass_prompt" ]; then
      read -p $'\nDo you want to remove image? (yes|no): ' dkr_rmi
    else
      dkr_rmi=$bypass_prompt
    fi

    case "$dkr_rmi" in
      yes|y)
        if docker image inspect $DL_OCI_IMAGE &> /dev/null; then
          echo -e "${RED}Deleting existing image...${RESET}"
          if docker rmi $DL_OCI_IMAGE; then
            echo -e "${GREEN}Image successfully deleted.${RESET}"
          else
            echo -e "${RED}Failed to delete image.${RESET}"
            return 1
          fi
        else
          echo -e "${YELLOW}Image $DL_OCI_IMAGE does not exist.${RESET}"
        fi
        ;;
      no|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${RED}Invalid choice. Exiting function...${RESET}\n"
        return 1
        ;;
    esac

    if [ $? -eq 0 ]; then
      echo -e "${GREEN}Operation successful.${RESET}"
      return 0
    else
      echo -e "${RED}Operation aborted.${RESET}"
      return 1
    fi
  }

  # function to build docker image
  function dkr_build_image {
    local bypass_prompt=$1
    if [ -z "$bypass_prompt" ]; then
      read -p $'\nDo you want to build image? (yes|no): ' dkr_build
    else
      dkr_build=$bypass_prompt
    fi

    case "$dkr_build" in
      yes|y)
        if grep -q "^NODE_ENV=" "$dotenv"; then
          echo -e "Building ${GREEN}$DL_OCI_IMAGE${RESET} image"
          echo -e "Value of NODE_ENV: $NODE_ENV"
          
          # Link Dockerfile and .dockerignore
          ln -sf ./ops/dkr/Dockerfile Dockerfile
          ln -sf ./ops/dkr/.dockerignore .dockerignore

          # If DL_DKR_ENV is set and non-empty, build --build-arg options and update Dockerfile
          if [ -n "$DL_DKR_ENV" ]; then
            build_args=""
            # Generate the env snippet for the Dockerfile dynamically
            env_snippet="#env"
            IFS=',' read -r -a env_keys <<< "$DL_DKR_ENV"
            for key in "${env_keys[@]}"; do
              key=$(echo "$key" | xargs)  # Trim whitespace
              build_args+=" --build-arg ${key}=${!key}"
              env_snippet+="\nARG ${key}"
            done
            for key in "${env_keys[@]}"; do
              key=$(echo "$key" | xargs)
              env_snippet+="\nENV ${key}=\$${key}"
            done

            echo -e "Using build args: $build_args"
            echo -e "Updating Dockerfile with:\n$env_snippet"
            
            # Write the snippet to a temporary file
            tmp_snippet=$(mktemp)
            echo -e "$env_snippet" > "$tmp_snippet"
            
            # Insert the snippet after the line containing "COPY ./app ."
            sed -i "/COPY \.\/app \./r $tmp_snippet" Dockerfile
            
            # Remove the temporary snippet file
            rm "$tmp_snippet"

            docker build $build_args -t $DL_OCI_IMAGE . 2> build_errors.log
          else
            docker build -t $DL_OCI_IMAGE . 2> build_errors.log
          fi
        else
          echo -e "${GREEN}Building $DL_OCI_IMAGE image${RESET}"
          ln -sf ./ops/dkr/Dockerfile Dockerfile
          ln -sf ./ops/dkr/.dockerignore .dockerignore
          docker build --no-cache -t $DL_OCI_IMAGE . 2> build_errors.log
        fi
        if [ $? -eq 0 ]; then
          if docker image inspect $DL_OCI_IMAGE &> /dev/null; then
            echo -e "\nDocker image ${GREEN}$DL_OCI_IMAGE${RESET} built successfully\n"
            rm -f Dockerfile .dockerignore build_errors.log
            return 0
          else
            echo -e "${RED}Error: Image built but not found${RESET}\n"
            cat build_errors.log
            rm -f Dockerfile .dockerignore build_errors.log
            exit 1
          fi
        else
          echo -e "${RED}Error: Cannot build image${RESET}\n"
          cat build_errors.log
          rm -f Dockerfile .dockerignore build_errors.log
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${RED}Invalid choice. Exiting function...${RESET}\n"
        return 1
        ;;
    esac
  }

  dkr_purge_image yes
  if [ $? -ne 0 ]; then
    echo -e "${RED}Error in purging images.${RESET}"
    return 1
  fi

  dkr_rmi_image no
  if [ $? -ne 0 ]; then
    echo -e "${RED}Error in removing images.${RESET}"
    return 1
  fi

  dkr_build_image yes
  if [ $? -ne 0 ]; then
    echo -e "${RED}Error in building image.${RESET}"
    return 1
  fi
}


#9 create github workflow
function ga_workflow_env {
  read -p $'\nDo you want to create workflow env? (yes|no): ' ga_workflow
  case "$ga_workflow" in
    yes|Y|y)
      # check if argument is provided
      if [ $# -ne 1 ]; then
        read -p $'\nEnvfile not found... Enter path to env file: ' env
        envfile="$env"
      else
        envfile="$1"
      fi

      vfile="./ops/vars.txt"
      ga_file1="deploy.yml"
      ga_file2="deploy_new.yml"
      ga_dir="./.github/workflows"
      ga="$ga_dir/$ga_file1"
      ga_new="$ga_dir/$ga_file2"

      # Delete vars.txt if it exists
      if [ -f $vfile ]; then
        rm $vfile
      fi

      # Read .env file
      IFS=' ' read -r -a exclude <<< "$DL_ENV_EXCLUDE"
      while IFS= read -r kv; do
        key=$(echo "$kv" | cut -d= -f1)
        if [[ " ${exclude[@]} " =~ " $key " ]]; then
          continue
        fi
        if [[ $key != "" && $key != "#"* ]]; then
          echo "$key" >> $vfile
        fi
      done < <(grep '=' $envfile)

      # Load variables from vars.txt
      while read -r var; do
        vars+=($var)
      done < $vfile

      # Find the "Generate envfile" step in deploy.yml
      envfile_line=$(grep -n "uses: SpicyPizza/create-envfile@v2.0" $ga | cut -d: -f1)
      envfile_line=$((envfile_line+1))
      tail_line=$(grep -n "directory: \${{ env.DL_ENV_SRC }}" $ga | cut -d: -f1)

      # Generate new file with variables
      {
        head -n $((envfile_line)) $ga
        for var in "${vars[@]}"; do
          echo "          envkey_$var: \${{ secrets.$var }}" 
        done
        tail -n +$((tail_line)) $ga
      } > $ga_new

      # Overwrite original 
      mv $ga_new $ga
      rm -f $vfile
      echo -e "${GREEN}Actions worklow updated successfully!${RESET}\n"
      ;;
    no|N|n)
      echo -e "${GREEN}Alright. Thank you...${RESET}\n"
      ;;
    *)
      echo -e "${GREEN}No choice. Exiting script...${RESET}"
      ;;
  esac
}

#10 set gh secrets
function gh_secret_set {
  # function to set secrets on private GitHub repo
  function gh_secret_private {
    read -p $'\nDo you want to set secrets on private repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        # check if argument is provided
        if [ $# -ne 1 ]; then
          read -p $'\nEnvfile not found... Enter path to env file: ' env
          envfile="$env"
        else
          envfile="$1"
        fi

        # Set number of retries and delay between retries  
        MAX_RETRIES=3
        RETRY_DELAY=2
        # Helper function to retry command on failure
        retry() {
          local retries=$1
          shift
          local count=0
          until "$@"; do
            exit=$?
            count=$(($count + 1))
            if [ $count -lt $retries ]; then
              echo "Command failed! Retrying in $RETRY_DELAY seconds..."
              sleep $RETRY_DELAY 
            else
              echo "Failed after $count retries."
              return $exit
            fi
          done 
          return 0
        }

        echo -e "${GREEN}Setting secrets...${RESET}\n"
        # Read the .env file and set the secrets
        retry $MAX_RETRIES gh secret set -f "$envfile"
        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Secrets set successfully\n"
        else
          echo -e "Error setting secrets\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  # function to delete secrets on private GitHub repo
  function gh_secret_private_rm {
    read -p $'\nDo you want to delete secrets on private repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        echo -e "${GREEN}Deleting private repo secrets...${RESET}\n"
        # Get list of secrets 
        secrets=$(gh secret list --repo ${DL_GH_OWNER_REPO} --json name --jq '.[].name')

        # Read secrets into array
        SECRETS=()
        while IFS= read -r secret; do
          SECRETS+=("$secret") 
        done <<< "$secrets"

        # Delete secrets
        for secret in "${SECRETS[@]}"; do
          gh secret delete --repo ${DL_GH_OWNER_REPO} "$secret"
        done

        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Secrets deleted successfully\n"
        else
          echo -e "Error deleting secrets\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  # function to set secrets on public GitHub repo
  function gh_secret_public {
    read -p $'\nDo you want to set secrets on public repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        # check if argument is provided
        if [ $# -ne 1 ]; then
          read -p $'\nEnvfile not found... Enter path to env file: ' env
          envfile="$env"
        else
          envfile="$1"
        fi

        # Set number of retries and delay between retries  
        MAX_RETRIES=3
        RETRY_DELAY=2
        # Helper function to retry command on failure
        retry() {
          local retries=$1
          shift
          local count=0
          until "$@"; do
            exit=$?
            count=$(($count + 1))
            if [ $count -lt $retries ]; then
              echo -e "Command failed! Retrying in $RETRY_DELAY seconds..."
              sleep $RETRY_DELAY 
            else
              echo -e "Failed after $count retries."
              return $exit
            fi
          done 
          return 0
        }

        echo -e "${GREEN}Setting secrets...${RESET}\n"
        # Check the DL_GH_BRANCH variable
        if [ "$DL_GH_BRANCH" = "release/ec2-prod" ]; then
          env="prod"
        elif [ "$DL_GH_BRANCH" = "release/ec2-dev" ]; then
          env="dev"
        else
          echo "DL_GH_BRANCH value not what is expected!"
          exit 0
        fi
        # Read the .env file and set the secrets
        retry $MAX_RETRIES gh secret set -f "$envfile" -e "$env"
        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Secrets set successfully\n"
        else
          echo -e "Error setting secrets\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  # function to delete secrets on public GitHub repo
  function gh_secret_public_rm {
    read -p $'\nDo you want to delete secrets on public repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        echo -e "${GREEN}Deleting public repo secrets...${RESET}\n"
        # Check the DL_GH_BRANCH variable
        if [ "$DL_GH_BRANCH" = "release/ec2-prod" ]; then
          env="prod"
        elif [ "$DL_GH_BRANCH" = "release/ec2-dev" ]; then
          env="dev"
        else
          echo "Aha! No need then..."
          exit 0
        fi

        # Get list of secrets 
        secrets=$(gh secret list --repo ${DL_GH_OWNER_REPO} --env $env --json name --jq '.[].name')

        # Read secrets into array
        SECRETS=()
        while IFS= read -r secret; do
          SECRETS+=("$secret") 
        done <<< "$secrets"

        # Delete secrets
        for secret in "${SECRETS[@]}"; do
          gh secret delete --repo ${DL_GH_OWNER_REPO} --env $env "$secret"
        done

        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Secrets deleted successfully\n"
        else
          echo -e "Error deleting secrets\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  # function to set variables on private GitHub repo
  function gh_variable_private {
    read -p $'\nDo you want to set variables on private repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        echo -e "${GREEN}Setting variables...${RESET}\n"
        vhost=${DL_NGX_VHOST}
        gh variable set DL_NGX_VHOST < "$vhost"
        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Variables set successfully\n"
        else
          echo -e "Error setting variables\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  # function to delete variables on private GitHub repo
  function gh_variable_private_rm {
    read -p $'\nDo you want to delete variables on private repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        echo -e "${GREEN}Deleting variables...${RESET}\n"
        gh variable delete DL_NGX_VHOST --repo ${DL_GH_OWNER_REPO}

        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Variables deleted successfully\n"
        else
          echo -e "Error deleting variables\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  # function to set variables on public GitHub repo
  function gh_variable_public {
    read -p $'\nDo you want to set variables on public repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        echo -e "${GREEN}Setting variables...${RESET}\n"
        # Check the DL_GH_BRANCH variable
        if [ "$DL_GH_BRANCH" = "release/ec2-prod" ]; then
          env="prod"
        elif [ "$DL_GH_BRANCH" = "release/ec2-dev" ]; then
          env="dev"
        else
          echo "Haa! No need then..."
          exit 0
        fi
        vhost=${DL_NGX_VHOST}
        gh variable set DL_NGX_VHOST < "$vhost" -e"$env"
        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Variables set successfully\n"
        else
          echo -e "Error setting variables\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  # function to delete variables on public GitHub repo
  function gh_variable_public_rm {
    read -p $'\nDo you want to delete variables on public repo? (yes|no): ' git_push
    case "$git_push" in
      yes|Y|y)
        echo -e "${GREEN}Deleting variables...${RESET}\n"
        # Check the DL_GH_BRANCH variable
        if [ "$DL_GH_BRANCH" = "release/ec2-prod" ]; then
          env="prod"
        elif [ "$DL_GH_BRANCH" = "release/ec2-dev" ]; then
          env="dev"
        else
          echo "Haa! No need then..."
          exit 0
        fi

        gh variable delete DL_NGX_VHOST --repo ${DL_GH_OWNER_REPO} --env $env

        # Check return code and output result
        if [ $? -eq 0 ]; then
          echo -e "Variables deleted successfully\n"
        else
          echo -e "Error deleting variables\n"
          exit 1
        fi
        ;;
      no|N|n)
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }

  check="$(gh_repo_view)"
  if [ "$check" == "private" ]; then
    gh_secret_private_rm
    gh_secret_private $DL_APP_ENV_FILE
    gh_variable_private_rm
    gh_variable_private
  elif [ "$check" == "public" ]; then
    gh_secret_public_rm
    gh_secret_public $DL_APP_ENV_FILE
    gh_variable_public_rm
    gh_variable_public
  else
    echo "Could not set secrets. Something is wrong!"
    exit 1
  fi
}

#11 push commit to remote git server
function git_repo_push {
  read -p $'\nDo you want to push your commit to origin? (yes|no): ' git_push
  case "$git_push" in
    yes|Y|y)
      echo -e "${GREEN}Pushing commit to GitHub...${RESET}\n"
      git push
      ;;
    no|N|n)
      echo -e "${GREEN}Alright. Thank you...${RESET}\n"
      ;;
    *)
      echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
      exit 1
      ;;
  esac
}

function docker_push {
  local bypass_prompt=$1

  # which git branch?
  git_branch

  if [ -z "$bypass_prompt" ]; then
      read -p $'\nDo you want to push docker image? (yes|no): ' dkr_push
  else
      dkr_push=$bypass_prompt
  fi

  case "$dkr_push" in
    yes|y)
      # echo ${DL_DK_TOKEN} | docker login -u ${DL_DK_HUB} --password-stdin
      if echo ${DL_GITEA_TOKEN} | docker login -u ${DL_GITEA_ADMIN} ${DL_REGISTRY_URL} --password-stdin; then
        if docker push $DL_OCI_IMAGE; then
          echo -e "${GREEN}Docker image successfully pushed to ${DL_REGISTRY_URL}${RESET}"
        else
          echo -e "${RED}Failed to push Docker image${RESET}"
          return 1
        fi
      else
        echo -e "${RED}Failed to login to Docker registry${RESET}"
        exit 1
      fi
      ;;
    no|n)
      echo -e "${GREEN}Alright. Thank you...${RESET}"
      ;;
    *)
      echo -e "${RED}Invalid choice. Exiting function...${RESET}"
      return 1
      ;;
  esac
}


#---------------------------------------#
# github actions                        #
#---------------------------------------#
#13 create dns record on aws route53
function create_route53_record {
  # Load environment variables from a .env file
  # Variables from .env or directly assigned
  HOSTED_ZONE_ID="$DL_AWS_R53_ZONEID"
  DNS_NAME="$DL_APP_URL2"
  DNS_TYPE="${DNS_TYPE:-A}"
  DNS_TTL="${DNS_TTL:-60}"
  DNS_VALUE="$DL_AWS_R53_IP"

  # Function to check if DNS record exists and get its current value
  check_dns_record() {
    local hosted_zone_id=$1
    local dns_name=$2
    local dns_type=$3

    aws route53 list-resource-record-sets \
      --profile dclmict \
      --hosted-zone-id "$hosted_zone_id" \
      --query "ResourceRecordSets[?Name == '$dns_name.' && Type == '$dns_type']" \
      --output json
  }

  # Function to create or update DNS record
  modify_dns_record() {
    local hosted_zone_id=$1
    local dns_name=$2
    local dns_type=$3
    local dns_ttl=$4
    local dns_value=$5
    local action=$6

    change_batch=$(jq -n --arg action "$action" --arg name "$dns_name." --arg type "$dns_type" --arg ttl "$dns_ttl" --arg value "$dns_value" '{
      "Comment": "Modify record via script",
      "Changes": [
        {
          "Action": $action,
          "ResourceRecordSet": {
            "Name": $name,
            "Type": $type,
            "TTL": ($ttl | tonumber),
            "ResourceRecords": [
              {
                "Value": $value
              }
            ]
          }
        }
      ]
    }')

    aws route53 change-resource-record-sets \
      --profile dclmict \
      --hosted-zone-id "$hosted_zone_id" \
      --change-batch "$change_batch"
  }

  # Check if DNS record exists and get its current value
  record_info=$(check_dns_record "$HOSTED_ZONE_ID" "$DNS_NAME" "$DNS_TYPE")
  
  if [ -z "$record_info" ]; then
    echo "Error: Could not retrieve DNS record information. Please check your AWS CLI configuration."
    return 1
  fi

  record_count=$(echo "$record_info" | jq '. | length')
  
  if [ "$record_count" -gt 0 ]; then
    current_value=$(echo "$record_info" | jq -r '.[0].ResourceRecords[0].Value')
    if [ "$current_value" = "$DNS_VALUE" ]; then
      echo "DNS record $DNS_NAME of type $DNS_TYPE already exists with the correct value."
    else
      echo "DNS record $DNS_NAME of type $DNS_TYPE exists but has a different value. Updating it."
      if modify_dns_record "$HOSTED_ZONE_ID" "$DNS_NAME" "$DNS_TYPE" "$DNS_TTL" "$DNS_VALUE" "UPSERT"; then
        echo "DNS record $DNS_NAME of type $DNS_TYPE updated successfully."
      else
        echo "Failed to update DNS record $DNS_NAME of type $DNS_TYPE."
        return 1
      fi
    fi
  else
    echo "DNS record $DNS_NAME of type $DNS_TYPE does not exist. Creating it."
    if modify_dns_record "$HOSTED_ZONE_ID" "$DNS_NAME" "$DNS_TYPE" "$DNS_TTL" "$DNS_VALUE" "CREATE"; then
      echo "DNS record $DNS_NAME of type $DNS_TYPE created successfully."
    else
      echo "Failed to create DNS record $DNS_NAME of type $DNS_TYPE."
      return 1
    fi
  fi
}


#14 create directory to deploy app  
function create_app_dir {
  # Navigate into the docker directory
  cd "$DL_APP_DK_DIR"

  # Check if target folder exists
  if [ ! -d "$DL_APP_NAME" ]; then
    # Folder doesn't exist, create it
    echo "Creating folder $DL_APP_NAME"  
    mkdir -p "$DL_APP_NAME"
  else
    # Folder exists, print message
    echo "Folder $DL_APP_NAME already exists"
  fi
}

#15 clone app repository 
function clone_app_repo {
  # Check app dir
  echo -e "\nChecking if app directory exists.."
  if [ ! -d "$DL_APP_DIR" ]; then
    echo "Directory not found, creating..."
    mkdir -p "$DL_APP_DIR"
  else
    echo "Directory already exists."
  fi

  # Enter into app dir
  echo -e "\nEntering app directory.."
  cd "$DL_APP_DIR"

  # Clone app repo
  echo -e "\nCloning latest repo changes.."
  if [ ! -d .git ]; then
    echo "App repo not found. Cloning..."
    git clone "$DL_GH_REPO" . \
    && git switch "$DL_GH_BRANCH"
  else
    echo "App repo exists..."
    git fetch --all \
    && git switch "$DL_GH_BRANCH"
  fi
}

#16 create nginx vhost for app url
function create_nginx_vhost {
  # enter directory
  cd "$DL_ENV_DEST"

  # another way
  ngxx="vhost.conf"
  ngx=$(cat "$ngxx")
  eval "VHOST=\"$ngx\""

  # Create a temporary file with the provided configuration
  echo -e "\nCreating temporary file..."
  temp_file="$(mktemp)"
  echo "$VHOST" > "$temp_file"

  # Extract the block identifier (the first line of the provided config)
  echo -e "\nExtracting the vhost block identifier..."
  block_identifier=$(head -n 1 "$temp_file")
  echo -e "Content of block identifier:\n$block_identifier"

  # Check if the vhost configuration exists
  echo -e "\nChecking if vhost config exists..."
  if grep -qF "$block_identifier" "$DL_HOST_NGX_DIR/$DL_NGX_CONF"; then
    echo -e "Vhost config already exists."

    # Get the existing vhost block that matches the block identifier
    echo -e "\nExtracting existing vhost config..."
    end_pattern="^}"
    existing_block="$(sed -n "/$block_identifier/,/$end_pattern/p" "$DL_HOST_NGX_DIR/$DL_NGX_CONF")"
    echo -e "Content of existing vhost:\n$existing_block"

    # Compare the existing block with the provided configuration
    echo -e "\nComparing existing vhost config with provided vhost config..."
    if diff -q <(echo "$VHOST") <(echo "$existing_block"); then
      echo "Configuration matches. No action needed."
    else
      # Delete the existing vhost configuration and append the provided config
      echo -e "\nDeleting existing vhost config..."
      sed -i "/$block_identifier/,/$end_pattern/d" "$DL_HOST_NGX_DIR/$DL_NGX_CONF"
      echo -e "\nUpdating vhost config..."
      echo -e "\n$VHOST" | sudo tee -a "$DL_HOST_NGX_DIR/$DL_NGX_CONF"
      echo "Nginx vhost configuration updated."

      # Test Nginx configuration for syntax errors
      sudo nginx -t

      # Reload Nginx if the configuration is valid
      if [ $? -eq 0 ]; then
        sudo nginx -s reload
        sudo systemctl status nginx
      else
        echo "Nginx configuration is invalid. Not reloading Nginx."
      fi
    fi
  else
    echo "Nginx vhost configuration not found."
    echo "Creating Nginx vhost entry for $DL_APP_URL..."
    echo -e "\n$VHOST" | sudo tee -a "$DL_HOST_NGX_DIR/$DL_NGX_CONF"

    # Test Nginx configuration for syntax errors
    sudo nginx -t

    # Reload Nginx if the configuration is valid
    if [ $? -eq 0 ]; then
      sudo nginx -s reload
      sudo systemctl status nginx
    else
      echo "Nginx configuration is invalid. Not reloading Nginx."
    fi  
  fi

  # Remove temporary files
  echo -e "\nRemoving temporary files..."
  rm -f "$temp_file"
  rm -f "$ngxx"
}

#17 deploy app on prod server
function ga_deploy_app {
  # Enter app dir
  echo -e "\nEntering app directory..."
  cd "$DL_APP_DIR"

  # Pull repo changes
  echo -e "\nDownloading latest repo changes..."
  make new

  # Drop running container
  echo -e "\nDropping running container..."
  make down

  # Start new container
  echo -e "\nLaunching latest app version..."
  make run
}

#---------------------------------------#
# utils                                 #
#---------------------------------------#
#18 function to copy .env based on environment
function copy_app_env {
  # Define the source and destination directories
  src_dir="./ops"
  dest_dir="./app"

  # Define environment file
  dest_env=".env"
  default_env_file="bams.env"

  # Display the options
  echo "Please select an environment:"
  echo "1) dclm-dev"
  echo "2) dclm-prod"
  echo "3) Custom env"

  # Read the user's selection
  read -p "Select an option or press enter to copy default: " selection

  # Handle the user's selection
  case $selection in
    1)
      env_file="dclm-dev.env"
      ;;
    2)
      env_file="dclm-prod.env"
      ;;
    3)
      read -p "Enter the name of the custom environment file: " env_file
      ;;
    "")
      env_file=$default_env_file
      ;;
    *)
      echo -e "Invalid option. Please select 1, 2, or 3\n"
      ;;
  esac

  # Copy the environment file
  cp "${src_dir}/${env_file}" "${dest_dir}/${dest_env}"

  # Check if the copy was successful
  if [ $? -eq 0 ]; then
    echo -e "Environment file copied successfully.\n"
  else
    echo -e "Failed to copy environment file. Exiting.\n"
    exit 1
  fi
}

#19 function to scan GitHub repo
function git_repo_scan {
	read -p $'\nDo you want to scan this repo? (yes|no): ' repo_scan
	case "$$repo_scan" in
		yes|Y|y)
			echo -e "${GREEN}Scanning repo for secrets...${RESET}\n"
			ggshield secret scan repo .
			;;
		no|N|n)
			echo -e "${GREEN}Okay. Thank you...${RESET}\n"
			exit 0
			;;
		*)
			echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
			exit 1
			;;
	esac  
}

#20 function to rename local git repo
function git_repo_rename {
  echo -e "I love JESUS"
}

#21 function to rename GitHub repo
function gh_repo_rename {
  read -p "Enter GitHub username: " gh_user

  function repo_name {
    read -p "Enter current repository name: " gh_repo
    read -p "Enter new repository name: " new_name
    # API to rename repo
    API_ENDPOINT="https://api.github.com/repos/${gh_user}/${gh_repo}"

    # Make API call to rename repo
    curl \
      -X PATCH \
      -H "Authorization: token ${DL_GH_TOKEN}" \
      -d '{"name":"'"${new_name}"'"}' \
      ${API_ENDPOINT}

    if [ $? -eq 0 ]; then
      echo -e "Repository renamed successfully!\n"
    else
      echo -e "Error renaming repository\n" >&2
      exit 1
    fi

    # run function to change repo remote url
    repo_url
  }

  function repo_url {
    read -p $'\nAbout to change repo"s remote url. Proceed? (yes|no): ' user_grant
    case "$user_grant" in
      yes|Y|y)
        read -p "Enter new repository name: " NEW_NAME
        git remote set-url origin git@github.com:${GH_USER}/${NEW_NAME}.git
        git remote -v
        if [ $? -eq 0 ]; then
          echo "Remote url successfully set!"
        else
          echo "Error renaming repository" >&2
          exit 1
        fi
        ;; 
      no|N|n) 
        echo -e "${GREEN}Alright. Thank you...${RESET}\n"
        exit 0
        ;;
      *)
        echo -e "${GREEN}No choice. Exiting script...${RESET}\n"
        exit 1
        ;;
    esac
  }
  # Select action
  echo "Select action:"
  echo "1) Rename repo name on Github"
  echo "2) Rename repo remote url"
  read action_selection
  if [ $action_selection -eq 1 ]; then
    repo_name
  elif [ $action_selection -eq 2 ]; then
    repo_url
  else
    echo "Invalid selection"
    exit 1  
  fi
}

#22 function to check if GitHub repo exists
function gh_repo_check {
  # check if argument is provided
  if [ $# -ne 1 ]; then
    read -p "Enter GitHub username: " ghUser
		read -p "Enter GitHub repo name: " ghName
    repo="${ghUser}/${ghName}"
  else
    repo=$1
  fi

  status_code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token ${DL_GH_TOKEN}" "https://api.github.com/repos/$repo")

  code1=200
  code2=404

  if [ $status_code -eq 200 ]; then
    echo $code1
  elif [ $status_code -eq 404 ]; then
    echo $code2
  else
    echo "Status code: $status_code" >&2
    exit 1
  fi
}

#23 function to check if GitHub repo is private/public
function gh_repo_view {
  code1=private
  code2=public
  view=$(gh repo view $DL_GH_OWNER_REPO --json isPrivate -q .isPrivate 2>/dev/null)
	if [ "$view" = "true" ]; then
		echo $code1
	else
		echo $code2
	fi
}


#---------------------------------------#
# git push                  #
#---------------------------------------#
function git_push {
  git_branch
  ga_workflow_env $dotenv
  commit_status
  gh_secret_set
  git_repo_push
}


# 24 function to create environment secrets on gitea repo
function gitea_env {
  # source $dotenv
  which=$1

  # Function to create a secret
  create_secret() {
    local secret_name="$1"
    local secret_value="$2"

    # Data payload for creating a secret
    local data=$(printf '{"data": "%s"}' "$secret_value")

    # Determine the correct API endpoint based on the scope
    # if [ "$3" = "org" ]; then
    #   endpoint="$DL_GITEA_API_URL/orgs/$DL_GITEA_ORG/actions/secrets/$secret_name"
    # elif [ "$3" = "repo" ]; then
    #   endpoint="$DL_GITEA_API_URL/repos/$DL_GITEA_OWNER/$DL_REPO_NAME/actions/secrets/$secret_name"
    # else
    #   echo "Invalid scope: $3"
    #   return 1
    # fi

    endpoint="$DL_GITEA_API_URL/repos/$DL_GITEA_OWNER/$DL_REPO_NAME/actions/secrets/$secret_name"

    # Debug: Print the data payload and endpoint
    # echo "Creating secret '$secret_name' with endpoint '$endpoint'"
    # echo "Payload: $data"

    # Make the API request to create the secret
    response=$(curl --cacert ~/dev/keys/dclm.hq/dclm.hq.crt -s -o /dev/null -w "%{http_code}" -X PUT "$endpoint" \
      --header "Authorization: token $DL_GITEA_TOKEN" \
      --header "Content-Type: application/json" \
      --data-raw "$data")

    if [ "$response" = 201 ] || [ "$response" = 204 ]; then
      echo "Secret '$secret_name' created successfully."
    else
      echo "Failed to create secret '$secret_name'. HTTP response code: $response"
    fi
  }

  # Read the .env file and create secrets
  while IFS='=' read -r secret_name secret_value || [ -n "$secret_name" ]; do
    # Skip empty lines and comments
    if [ -z "$secret_name" ] || [[ "$secret_name" == \#* ]]; then
      continue
    fi

    # Evaluate the value to replace variables with their actual values
    eval expanded_secret=\$$secret_name
    create_secret "$secret_name" "$expanded_secret"
    # create_secret "$secret_name" "$expanded_secret" "$which"
  done < "$dotenv"
}


function mikrotik_dns {
  # source $dotenv

  # Set the command to check for the DNS name
  CHECK="/ip dns static print where name=$MK_DNS_NAME"

  # Set the command to run on the Mikrotik server
  CREATE="/ip dns static add address=$MK_DNS_ADDRESS comment=\"$MK_DNS_COMMENT\" name=$MK_DNS_NAME"

  # Check if the DNS entry already exists
  if [ "$(hostname)" == "bams" ]; then
    ssh -i ~/dev/keys/dles $MK_USER@$MK_HOST "$CHECK" | grep $MK_DNS_NAME > /dev/null

    if [ $? -eq 0 ]; then
      echo "Domain: ${MK_DNS_NAME} already exists. No action taken."
    else
      # Add the DNS entry
      ssh -i ~/dev/keys/dles $MK_USER@$MK_HOST "$CREATE"

      if [ $? -eq 0 ]; then
        echo "Domain: ${MK_DNS_NAME} has been added successfully"
      else
        echo "Failed to add domain ${MK_DNS_NAME}"
        exit 1
      fi
    fi
  else
    # Example SSH key stored in an environment variable
    SSH_CERT="$DLES_SSH_KEY"
    echo $SSH_CERT

    # Path to temporary file for the SSH key
    TMP_SSH_KEY=$(mktemp)

    # Write the SSH key to the temporary file
    echo "$SSH_CERT" > "$TMP_SSH_KEY"
    chmod 600 "$TMP_SSH_KEY"

    echo $TMP_SSH_KEY
    # Use the temporary SSH key to execute the command on the remote host
    ssh -i "$TMP_SSH_KEY" -T -o "StrictHostKeyChecking=no" "$MK_USER@$MK_HOST" "$CHECK" | grep $MK_DNS_NAME > /dev/null

    if [ $? -eq 0 ]; then
      echo "Domain: ${MK_DNS_NAME} already exists. No action taken."
    else
      # Add the DNS entry
      ssh -i "$TMP_SSH_KEY" -T -o "StrictHostKeyChecking=no" $MK_USER@$MK_HOST "$CREATE"

      if [ $? -eq 0 ]; then
        echo "Domain: ${MK_DNS_NAME} has been added successfully"
      else
        echo "Failed to add domain ${MK_DNS_NAME}"
        exit 1
      fi
    fi

    # Clean up by removing the temporary SSH key file
    rm "$TMP_SSH_KEY"
  fi
}

function gitea_workflow_secret {
  # Path to the .env file
  # dotenv='./.env'
  deploy_yml='./.gitea/workflows/deploy.yml'

  # Check if the .env file exists
  # if [ ! -f "$dotenv" ]; then
  #   echo ".env file not found!"
  #   exit 1
  # fi

  # Initialize an empty array to store the variable names
  env_vars=()

  # Read the .env file line by line
  while IFS= read -r line; do
    # Skip empty lines and comments
    if [ -z "$line" ] || [[ "$line" == \#* ]]; then
      continue
    fi

    # Extract the variable name
    var_name=$(echo "$line" | cut -d'=' -f1)
    
    # Add the variable name to the array
    env_vars+=("$var_name")
  done < "$dotenv"

  # Convert the array to a string in the desired format
  env_vars_string='          secrets=('  # 10 spaces before 'secrets=('
  for var in "${env_vars[@]}"; do
    env_vars_string+="\"$var\" "
  done
  env_vars_string=${env_vars_string% }')'

  # Escape any special characters in the replacement string for sed
  escaped_env_vars_string=$(printf '%s\n' "$env_vars_string" | sed 's/[&/\]/\\&/g')

  # Replace the line starting with 'secrets=(' in deploy.yml
  if [ -f "$deploy_yml" ]; then
    # Use a temporary file for the substitution
    tmpfile=$(mktemp)
    sed "s/^ *secrets=(\"DL_APP1\".*/$escaped_env_vars_string/" "$deploy_yml" > "$tmpfile" && mv "$tmpfile" "$deploy_yml"
    
    echo "Updated $deploy_yml with new secrets."
  else
    echo "$deploy_yml not found!"
    exit 1
  fi

}


#---------------------------------------#
# k8s                                   #
#---------------------------------------#
function set_kube_context() {
  local context=$1
  local namespace=$2
  if [ -z "$context" ]; then
    echo "Usage: set_kube_context <context-name> [namespace]"
    return 1
  fi

  # Check if the context exists
  if ! kubectl config get-contexts -o name | grep -q "^$context$"; then
    echo "Context '$context' does not exist. Available contexts are:"
    kubectl config get-contexts -o name
    return 1
  fi

  # Set the context
  kubectl config use-context "$context"
  
  # If namespace is provided, set it
  if [ -n "$namespace" ]; then
    kubectl config set-context --current --namespace="$namespace"
    echo "Context set to '$context' with namespace '$namespace'"
  else
    echo "Context set to '$context'"
  fi

  # Display current context info
  # kubectl config get-contexts --current
}

function is_pod_terminating() {
  local namespace=$1
  local pod_pattern=$2
  
  if [ -z "$namespace" ] || [ -z "$pod_pattern" ]; then
    echo "Usage: is_pod_terminating <namespace> <pod_pattern>"
    return 1
  fi

  local pod_name=$(kubectl get pods -n $namespace | grep $pod_pattern | awk '{print $1}')
  
  if [ -z "$pod_name" ]; then
    echo "No pod matching '$pod_pattern' found in namespace '$namespace'"
    return 1
  fi

  local deletion_timestamp=$(kubectl get pod -n $namespace $pod_name -o jsonpath='{.metadata.deletionTimestamp}')
  local phase=$(kubectl get pod -n $namespace $pod_name -o jsonpath='{.status.phase}')

  if [ -n "$deletion_timestamp" ] || [ "$phase" = "Terminating" ]; then
    echo "Pod $pod_name is terminating"
    return 0
  else
    echo "Pod $pod_name is not terminating"
    return 1
  fi
}

function delete_pod() {
  local namespace=$1
  local pod_pattern=$2
  
  if [ -z "$namespace" ] || [ -z "$pod_pattern" ]; then
    echo "Usage: delete_pod <namespace> <pod_pattern>"
    return 1
  fi

  local pod_name=$(kubectl get pods -n $namespace | grep $pod_pattern | awk '{print $1}')
  
  if [ -z "$pod_name" ]; then
    echo "No pod matching '$pod_pattern' found in namespace '$namespace'"
    return 1
  fi

  if is_pod_terminating $namespace $pod_pattern; then
    echo "Pod $pod_name is already terminating. No action taken."
    return 0
  else
    echo "Deleting pod: $pod_name"
    kubectl delete pod -n $namespace $pod_name
    if [ $? -eq 0 ]; then
      echo "Pod $pod_name deleted successfully"
      return 0
    else
      echo "Failed to delete pod $pod_name"
      return 1
    fi
  fi
}

function k8s_delete_pod {
  
  # check branch
  branch=$(git rev-parse --abbrev-ref HEAD)

  if [[ "$branch" = "release/k8s-dev" ]]; then
    delete_pod $K8S_NAMESPACE $DL_APP_NAME
  fi

  if [[ "$branch" = "release/dev" ]]; then
    delete_pod $K8S_NAMESPACE $DL_APP_NAME
  fi

  if [[ "$branch" = "release/prev" ]]; then
    delete_pod $K8S_NAMESPACE $DL_APP_NAME
  fi

}

function k8s_app_dev_deployment {
  # script to generate k8s manifest file from a template file
  # Usage: ./app.sh .env template.yml

  ENVFILE=$1
  OUTPUT_FILE=$2

  # Load the envfile
  if [[ -f "$ENVFILE" ]]; then
    source "$ENVFILE"
  else
    echo "Env file not found!"
    exit 1
  fi

  # Define the template
  read -r -d '' TEMPLATE << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${DL_APP_NAME}
  namespace: ${K8S_NAMESPACE}
spec:
  selector:
    matchLabels:
      app: ${DL_APP_NAME}
  template:
    metadata:
      labels:
        app: ${DL_APP_NAME}
    spec:
      containers:
      - name: ${DL_APP_NAME}
        image: ${DL_OCI_IMAGE}
        imagePullPolicy: Always
        resources:
          requests:
            cpu: "${K8S_CPU_REQ}"
            memory: "${K8S_MEMORY_REQ}"
          limits:
            cpu: "${K8S_CPU_LIMIT}"
            memory: "${K8S_MEMORY_LIMIT}"
        ports:
        - containerPort: ${K8S_CONTAINER_PORT}
        env:
      # imagePullSecrets:
      # - name: gitea
---
apiVersion: v1
kind: Service
metadata:
  name: ${DL_APP_NAME}
  namespace: ${K8S_NAMESPACE}
spec:
  selector:
    app: ${DL_APP_NAME}
  ports:
  - port: ${K8S_SERVICE_PORT}
    targetPort: ${K8S_CONTAINER_PORT}
EOF

  # Replace placeholders in the template
  eval "echo \"${TEMPLATE}\"" > "$OUTPUT_FILE"
  echo "Generated Kubernetes manifest saved to $OUTPUT_FILE"
}

function k8s_app_prod_deployment {
  # script to generate k8s manifest file from a template file
  # Usage: ./app.sh .env template.yml

  ENVFILE=$1
  OUTPUT_FILE=$2

  # Load the envfile
  if [[ -f "$ENVFILE" ]]; then
    source "$ENVFILE"
  else
    echo "Env file not found!"
    exit 1
  fi

  # Define the template
  read -r -d '' TEMPLATE << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${DL_APP_NAME}
  namespace: ${K8S_NAMESPACE}
spec:
  replicas: ${K8S_MIN_REPLICA}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 2
  selector:
    matchLabels:
      app: ${DL_APP_NAME}
  template:
    metadata:
      labels:
        app: ${DL_APP_NAME}
    spec:
      containers:
      - name: ${DL_APP_NAME}
        image: ${DL_OCI_IMAGE}
        imagePullPolicy: Always
        resources:
          requests:
            cpu: "${K8S_CPU_REQ}"
            memory: "${K8S_MEMORY_REQ}"
          limits:
            cpu: "${K8S_CPU_LIMIT}"
            memory: "${K8S_MEMORY_LIMIT}"
        ports:
        - containerPort: ${K8S_CONTAINER_PORT}
        env:
      # imagePullSecrets:
      # - name: gitea
---
apiVersion: v1
kind: Service
metadata:
  name: ${DL_APP_NAME}
  namespace: ${K8S_NAMESPACE}
spec:
  selector:
    app: ${DL_APP_NAME}
  ports:
  - port: ${K8S_SERVICE_PORT}
    targetPort: ${K8S_CONTAINER_PORT}
EOF

  # Replace placeholders in the template
  eval "echo \"${TEMPLATE}\"" > "$OUTPUT_FILE"
  echo "Generated Kubernetes manifest saved to $OUTPUT_FILE"
}

function k8s_app_deployment {
  # check for k8s directory
  if [ ! -d "./ops/k8s" ]; then
    mkdir ./ops/k8s
  fi
  # check branch
  branch=$(git rev-parse --abbrev-ref HEAD)

  if [[ "$branch" = "release/k8s-dev" ]]; then
    k8s_app_dev_deployment $dotenv ./ops/k8s/template.yml
  fi

  if [[ "$branch" = "release/dev" ]]; then
    k8s_app_dev_deployment $dotenv ./ops/k8s/template.yml
  fi

  if [[ "$branch" = "release/prev" ]]; then
    k8s_app_dev_deployment $dotenv ./ops/k8s/template.yml
  fi

  if [[ "$branch" = "release/k8s-prod" ]]; then
    k8s_app_prod_deployment $dotenv ./ops/k8s/template.yml
  fi

  if [[ "$branch" = "release/prod" ]]; then
    k8s_app_prod_deployment $dotenv ./ops/k8s/template.yml
  fi
}

function k8s_app_env {
  # script to add environment variables to a Kubernetes deployment manifest file
  # Usage: ./env.sh envfile template.yaml

  # Set the path to the environment variable file
  local ENVFILE=$1

  # Set the path to the Kubernetes deployment manifest file
  local DEPLOYMENT_FILE=$2
  local NEW_DEPLOYMENT_FILE=$3
  local TEMPLATE="./ops/k8s/template.yml"

  # Function to generate the environment variable entry
  generate_env_entry() {
      local key="$1"
      local value="$2"
      local secret_name=$DL_APP_NAME
      cat <<EOF
        - name: $key
          valueFrom:
            secretKeyRef:
              name: $secret_name
              key: $key
EOF
  }

  # Copy the original deployment file to a new file
  cp "$DEPLOYMENT_FILE" "$NEW_DEPLOYMENT_FILE"

  # Insert the generated env entries into the deployment YAML
  IFS=' ' read -r -a exclude <<< "$DL_ENV_EXCLUDE"
  while IFS='=' read -r key value; do
      # Skip lines starting with '#' or containing only spaces
      if [[ "$key" =~ ^#|^[[:space:]]*$ ]]; then
          continue
      fi
      # Check if the key is in the exclude list
      if [[ " ${exclude[@]} " =~ " $key " ]]; then
          continue
      fi
      env_entry=$(generate_env_entry "$key" "$value")
      sed -i -e "/        env:/r /dev/stdin" "$NEW_DEPLOYMENT_FILE" <<< "$env_entry"
  done < "$ENVFILE"

  echo "Environment variables added to the deployment file: $NEW_DEPLOYMENT_FILE"
  rm $TEMPLATE
}


function k8s_ingress_app() {
  ENVFILE=$1
  OUTPUT_FILE=$2

  # Load the envfile
  if [[ -f "$ENVFILE" ]]; then
  source "$ENVFILE"
  else
  echo "Env file not found!"
  exit 1
  fi

  # Function to generate an Ingress manifest.
  # Accepts one argument: merge_type (empty for default, or "master"/"minion")
  generate_ingress() {
    local merge_type="$1"
    local ingress_name="$INGRESS_NAME"
    if [ -n "$merge_type" ]; then
      ingress_name="${INGRESS_NAME}-${merge_type}"
    fi

    local result="apiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata:\n"

    # Metadata: name and namespace
    result+="  name: $ingress_name\n"
    result+="  namespace: $NAMESPACE\n"

    # Build annotations block
    local annotations=""
    if [ -n "$merge_type" ]; then
      annotations+="    nginx.org/mergeable-ingress-type: \"$merge_type\"\n"
    fi

    # Common annotation for both master and others
    if [ -n "$CLIENT_MAX_BODY_SIZE" ]; then
      annotations+="    nginx.org/client-max-body-size: \"$CLIENT_MAX_BODY_SIZE\"\n"
    fi

    # For default and minion (full ingress), include additional annotations
    if [ -z "$merge_type" ] || [ "$merge_type" = "minion" ]; then
      if [ -n "$SSL_REDIRECT" ]; then
        annotations+="    nginx.org/ssl-redirect: \"$SSL_REDIRECT\"\n"
      fi
      if [ -n "$REWRITE_TARGET" ]; then
        annotations+="    nginx.org/rewrite-target: \"$REWRITE_TARGET\"\n"
      fi
      if [ -n "$ALLOWED_IPS" ]; then
        annotations+="    custom.nginx.org/allowed-ips: \"$ALLOWED_IPS\"\n"
      fi
      if [ -n "$EXTERNAL_DNS_TARGET" ]; then
        annotations+="    external-dns.alpha.kubernetes.io/target: \"$EXTERNAL_DNS_TARGET\"\n"
      fi
      if [ -n "$REDIRECT_PATH" ] && [ -n "$REDIRECT_URL" ]; then
        annotations+="    nginx.org/location-snippets: |\n"
        IFS=',' read -r -a redirect_paths_array <<< "$REDIRECT_PATH"
        IFS=',' read -r -a redirect_urls_array <<< "$REDIRECT_URL"
        local len=${#redirect_paths_array[@]}
        for (( i=0; i<len; i++ )); do
          local path url
          path=$(echo "${redirect_paths_array[$i]}" | xargs)
          if [ -n "${redirect_urls_array[$i]}" ]; then
            url=$(echo "${redirect_urls_array[$i]}" | xargs)
          else
            url=$(echo "${redirect_urls_array[0]}" | xargs)
          fi
          annotations+="      if (\$request_uri ~* ^$path) {\n"
          annotations+="        return 302 $url;\n"
          annotations+="      }\n"
        done
      fi
    fi

    if [ -n "$annotations" ]; then
      result+="  annotations:\n"
      result+="$annotations"
    fi

    # Begin spec section
    result+="spec:\n"
    if [ -n "$INGRESS_CLASS" ]; then
      result+="  ingressClassName: $INGRESS_CLASS\n"
    fi

    # TLS block: only add if not a minion ingress
    if [ "$merge_type" != "minion" ] && [ -n "$TLS_HOSTS" ] && [ -n "$TLS_SECRET_NAMES" ]; then
      IFS=',' read -r -a tls_hosts_array <<< "$TLS_HOSTS"
      IFS=',' read -r -a tls_secrets_array <<< "$TLS_SECRET_NAMES"
      result+="  tls:\n"
      for i in "${!tls_hosts_array[@]}"; do
        local host secret
        host=$(echo "${tls_hosts_array[$i]}" | xargs)
        secret=$(echo "${tls_secrets_array[$i]}" | xargs)
        result+="    - hosts:\n"
        result+="        - $host\n"
        result+="      secretName: $secret\n"
      done
    fi

    # Rules block generation
    if [ "$merge_type" = "master" ]; then
      # For master, output a minimal rules block with only the host.
      local master_host=""
      if [ -n "$TLS_HOSTS" ]; then
        IFS=',' read -r -a tls_hosts_array <<< "$TLS_HOSTS"
        master_host=$(echo "${tls_hosts_array[0]}" | xargs)
      elif [ -n "$RULES" ]; then
        IFS=';' read -r -a rules_array <<< "$RULES"
        IFS=',' read -r master_host _ <<< "${rules_array[0]}"
        master_host=$(echo "$master_host" | xargs)
      fi
      if [ -n "$master_host" ]; then
        result+="  rules:\n"
        result+="  - host: $master_host\n"
      fi
    else
      # For minion and default, generate full rules with http paths.
      if [ -n "$RULES" ]; then
        result+="  rules:\n"
        IFS=';' read -r -a rules_array <<< "$RULES"
        declare -A host_rules
        for rule in "${rules_array[@]}"; do
          rule=$(echo "$rule" | xargs)
          IFS=',' read -r host path service port <<< "$rule"
          if [ -n "$host" ] && [ -n "$path" ] && [ -n "$service" ] && [ -n "$port" ]; then
            host_rules["$host"]+="$path,$service,$port;"
          fi
        done
        for host in "${!host_rules[@]}"; do
          result+="  - host: $host\n"
          result+="    http:\n"
          result+="      paths:\n"
          IFS=';' read -r -a paths_array <<< "${host_rules[$host]}"
          for entry in "${paths_array[@]}"; do
            if [ -n "$entry" ]; then
              IFS=',' read -r path service port <<< "$entry"
              result+="      - path: $path\n"
              result+="        pathType: Prefix\n"
              result+="        backend:\n"
              result+="          service:\n"
              result+="            name: $service\n"
              result+="            port:\n"
              result+="              number: $port\n"
            fi
          done
        done
      fi
    fi

    echo -e "$result"
  }

  # Main script logic
  final_output=""

  if [ -n "$INGRESS_TYPE" ]; then
    IFS=',' read -r -a types_array <<< "$INGRESS_TYPE"
    for type in "${types_array[@]}"; do
      type=$(echo "$type" | xargs)
      ingress_manifest=$(generate_ingress "$type")
      if [ -n "$final_output" ]; then
        final_output+="\n---\n"
      fi
      final_output+="$ingress_manifest"
    done
  else
    final_output=$(generate_ingress "")
  fi

  # Write the generated manifest to a file
  echo -e "$final_output" > $OUTPUT_FILE
  echo "Generated Ingress manifest saved to $OUTPUT_FILE"

}

function k8s_hpa_gen {
  # script to generate k8s manifest file from a template file
  # Usage: ./app.sh .env template.yml

  ENVFILE=$1
  OUTPUT_FILE=$2

  # Load the envfile
  if [[ -f "$ENVFILE" ]]; then
    source "$ENVFILE"
  else
    echo "Env file not found!"
    exit 1
  fi

  # Define the template
  read -r -d '' TEMPLATE << 'EOF'
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ${DL_APP_NAME}
  namespace: ${K8S_NAMESPACE}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ${DL_APP_NAME}
  minReplicas: ${K8S_MIN_REPLICA}
  maxReplicas: ${K8S_MAX_REPLICA}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: ${K8S_CPU_AVERAGE}
EOF

  # Replace placeholders in the template
  eval "echo \"${TEMPLATE}\"" > "$OUTPUT_FILE"
  echo "Autoscaling config successfully generated @ $OUTPUT_FILE"
}

function k8s_autoscaling {
  k8s_hpa_gen $dotenv ./ops/k8s/hpa.yml
}

function k8s_app_secret {
  # script to generate a Kubernetes secret from an envfile
  # Set the input envfile and output secret name
  ENVFILE=$1
  OUTPUT_FILE=$2

  # Create the secret YAML
  echo "apiVersion: v1
kind: Secret
metadata:
  name: $DL_APP_NAME
  namespace: $K8S_NAMESPACE
type: Opaque
data:" > $OUTPUT_FILE

  # Source the envfile to load variables into the environment
  if [[ -f "$ENVFILE" ]]; then
    set -a  # Automatically export all variables
    source "$ENVFILE"
    set +a
  else
    echo "Env file not found!"
    exit 1
  fi

  # Read environment variables from input_file and generate Kubernetes secret manifest
  while IFS='=' read -r key value; do
    if [[ $key != "#"* ]] && [[ -n "$key" ]]; then
      # Remove leading and trailing quotes from the value
      value=$(echo "$value" | sed 's/^"\(.*\)"$/\1/')

      # Evaluate the value to replace variables with their actual values
      eval expanded_value=\$$key

      # Encode the value in base64 and remove any newline characters
      encoded_value=$(echo -n "$expanded_value" | base64 | tr -d '\n')

      # Append the key and base64 encoded value to the output file
      echo "  $key: $encoded_value" >> $OUTPUT_FILE
    fi
  done < "$ENVFILE"

  if [ $? -eq 0 ]; then
    echo "Secret file generated to $OUTPUT_FILE"
  else
    echo "There's an issue generating secret from envfile."
  fi
}

function k8s_seal_app_secret {
  local SECRET=$1
  local KUBESEAL=$2
  # echo $SECRET
  /usr/local/bin/kubeseal --format yaml < $SECRET > $KUBESEAL
  mv ./ops/k8s/ssecret.yml ./ops/k8s/secret.yml > /dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "Secret sealed successfully"
  else
    echo "Error occured sealing secret."
  fi
}

function k8s_apply_manifest {
  local MANIFEST=$1
  kubectl apply -f $MANIFEST
}

function k8s_delete_manifests {
  local MANIFEST=$1
  kubectl --context $K8S_CONTEXT delete -f $MANIFEST
}

function stack() {
  if [ "$(hostname)" == "bams" ]; then
    source /Users/bamsd/dev/devops/🚀/sh/@.sh "$1"
  fi
}
function dev() {
  if [[ "$DL_APP_STACK" == "vitejs" ]]; then
    stack 2
  elif [[ "$DL_APP_STACK" == "nextjs" ]]; then
    stack 3
  elif [[ "$DL_APP_STACK" == "nodejs" ]]; then
    stack 4
  elif [[ "$DL_APP_STACK" == "nestjs" ]]; then
    stack 5
  fi
}

#---------------------------------------#
# CI/CD                                 #
#---------------------------------------#
function deploy_ci_cd {
  make
  gitea_env repo
  gitea_workflow_secret
  mikrotik_dns
  create_route53_record
}

#---------------------------------------#
# deploy to k8s                         #
#---------------------------------------#
function k8s_create_manifests {
  make
  # dev
  rm -rf ./ops/k8s/*
  k8s_app_deployment
  k8s_app_env $dotenv ./ops/k8s/template.yml ./ops/k8s/app.yml
  k8s_ingress_app $dotenv ./ops/k8s/ing.yml
  k8s_autoscaling
  k8s_app_secret $dotenv ./ops/k8s/secret.yml
}

function k8s_full_deploy {
  make
  dev
  commit_status
  set_kube_context $K8S_CONTEXT $K8S_NAMESPACE
  docker_build
  docker_push yes
  k8s_app_deployment
  k8s_app_env $dotenv ./ops/k8s/template.yml ./ops/k8s/app.yml
  k8s_ingress_app $dotenv ./ops/k8s/ing.yml
  k8s_autoscaling
  k8s_app_secret $dotenv ./ops/k8s/secret.yml
  k8s_seal_app_secret ./ops/k8s/secret.yml ./ops/k8s/ssecret.yml
  k8s_apply_manifest ./ops/k8s/
  k8s_delete_pod
}

function k8s_mini_deploy {
  make
  dev
  commit_status
  set_kube_context $K8S_CONTEXT $K8S_NAMESPACE
  k8s_app_deployment
  k8s_app_env $dotenv ./ops/k8s/template.yml ./ops/k8s/app.yml
  k8s_ingress_app $dotenv ./ops/k8s/ing.yml
  k8s_autoscaling
  k8s_app_secret $dotenv ./ops/k8s/secret.yml
  k8s_seal_app_secret ./ops/k8s/secret.yml ./ops/k8s/ssecret.yml
  k8s_apply_manifest ./ops/k8s/
  k8s_delete_pod
}

function k8s_minus_ingress {
  make
  dev
  commit_status
  set_kube_context $K8S_CONTEXT $K8S_NAMESPACE
  docker_build
  docker_push yes
  k8s_app_deployment
  k8s_app_env $dotenv ./ops/k8s/template.yml ./ops/k8s/app.yml
  k8s_autoscaling
  k8s_app_secret $dotenv ./ops/k8s/secret.yml
  k8s_seal_app_secret ./ops/k8s/secret.yml ./ops/k8s/ssecret.yml
  k8s_apply_manifest ./ops/k8s/
  k8s_delete_pod
}

# Check if a choice was provided as a command line argument
if [ $# -eq 0 ]; then
  # If no choice was provided, prompt for action
  echo "00) Nginx config"
  echo "01) Git: Create repo"
  echo "02) Git: Commit repo"
  echo "03) Git: Push repo"
  echo "04) Git: Scan repo"
  echo "05) Git: Rename repo" 
  echo "06) GitHub: Create repo"
  echo "07) GitHub: Rename repo"
  echo "08) GitHub: Check repo"
  echo "09) GitHub: View repo"
  echo "10) Gitea: Create repo env for CI/CD"
  echo "11) Gitea: Generate workflow for CI/CD"
  echo "12) Docker: Build image"
  echo "13) Docker: Push image"
  echo "14) DNS: Create route53 record"
  echo "15) APP: Create directory"
  echo "16) APP: Clone app repo"
  echo "17) APP: Copy app env"
  echo "18) Nginx: Create vhost"
  echo "19) Deploy app to server"
  echo "20) K8S: Generate app manifest"
  echo "21) K8S: Generate app env"
  echo "22) K8S: Generate app secret"
  echo "23) K8S: Seal secret with Kubeseal"
  echo "24) K8S: Apply manifest"
  echo "25) K8S: Delete pod"
  echo "26) DNS: Create record on Mikrotik"
  echo "27) Deploy app to EC2 instance"
  echo "28) CI/CD: Deploy"
  echo "29) K8S: Mini Deploy"
  echo "30) K8S: Full Deploy"
  echo "31) K8S: No Ingress"
  echo "32) K8S: Create deployment manifests"
  echo "33) K8S: Delete deployment manifests"
  echo "----------------------------------"
  read -p $'\nSelect action to perform [1-11, 21-30]: ' choice
else
  # If an argument is provided, use it
  choice="$1"
fi

if [ $choice -eq 0 ]; then
  nginx_config
elif [ $choice -eq 1 ]; then
  git_repo_create
elif [ $choice -eq 2 ]; then
  git_commit
elif [ $choice -eq 3 ]; then
  git_repo_push
elif [ $choice -eq 4 ]; then
  git_repo_scan
elif [ $choice -eq 5 ]; then
  git_repo_rename
elif [ $choice -eq 6 ]; then
  gh_repo_create
elif [ $choice -eq 7 ]; then
  gh_repo_rename
elif [ $choice -eq 8 ]; then
  gh_repo_check
elif [ $choice -eq 9 ]; then
  gh_repo_view
elif [ $choice -eq 10 ]; then
  gitea_env
elif [ $choice -eq 11 ]; then
  gitea_workflow_secret
elif [ $choice -eq 12 ]; then
  docker_build
elif [ $choice -eq 13 ]; then
  docker_push yes
elif [ $choice -eq 14 ]; then
  create_route53_record
elif [ $choice -eq 15 ]; then
  create_app_dir
elif [ $choice -eq 16 ]; then
  clone_app_repo
elif [ $choice -eq 17 ]; then
  copy_app_env
elif [ $choice -eq 18 ]; then
  create_nginx_vhost
elif [ $choice -eq 19 ]; then
  ga_deploy_app
elif [ $choice -eq 20 ]; then
  k8s_app_deployment $dotenv ./ops/k8s/template.yml
elif [ $choice -eq 21 ]; then
  k8s_app_env $dotenv ./ops/k8s/template.yml ./ops/k8s/app.yml
elif [ $choice -eq 22 ]; then
  k8s_app_secret $dotenv ./ops/k8s/secret.yml
elif [ $choice -eq 23 ]; then
  k8s_seal_app_secret ./ops/k8s/secret.yml ./ops/k8s/ssecret.yml
elif [ $choice -eq 24 ]; then
  k8s_apply_manifest ./ops/k8s/
elif [ $choice -eq 25 ]; then
  delete_pod $K8S_NAMESPACE $DL_APP_NAME
elif [ $choice -eq 26 ]; then
  mikrotik_dns
elif [ $choice -eq 27 ]; then
  deploy_dclm_ec2
elif [ $choice -eq 28 ]; then
  deploy_ci_cd
elif [ $choice -eq 29 ]; then
  k8s_mini_deploy
elif [ $choice -eq 30 ]; then
  k8s_full_deploy
elif [ $choice -eq 31 ]; then
  k8s_minus_ingress
elif [ $choice -eq 32 ]; then
  k8s_create_manifests
elif [ $choice -eq 33 ]; then
  k8s_delete_manifests ./ops/k8s/
else
  echo "Invalid selection"
  exit 1
fi
