deploy-app:
	@\
	echo "1. Push git repo"; \
	echo "2. Push docker image"; \
	read -p "Enter a number to select your choice: " deploy_app; \
	if [ $$deploy_app -eq 1 ]; then \
		./ops/sh/app.sh 5; \
	elif [ $$deploy_app -eq 2 ]; then \
		./ops/sh/app.sh 6; \
	else \
		echo "Invalid choice"; \
	fi


deploy:
	@\
	echo "1. Deploy to DCLM-EC2"; \
	echo "2. Deploy to DCLM-EKS"; \
	echo "3. Deploy to DLES-K8S"; \
	read -p "Enter a number to select your choice: " deploy; \
	if [ $$deploy -eq 1 ]; then \
		./ops/sh/app.sh 18; \
	elif [ $$deploy -eq 2 ]; then \
		./ops/sh/app.sh 19; \
	elif [ $$deploy -eq 3 ]; then \
		./ops/sh/app.sh 20; \
	else \
		echo "Invalid choice"; \
	fi
