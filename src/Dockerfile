FROM acr0ct0hub0weu0pas.azurecr.io/powershell:7.4-ubuntu-22.04 as base
ARG DEBIAN_FRONTEND=noninteractive
RUN useradd -ms /bin/bash app
RUN mkdir /opt/qa-testgen-interactive-dashboard-AI
RUN chmod -R 777 /opt/qa-testgen-interactive-dashboard-AI
WORKDIR /opt/qa-testgen-interactive-dashboard-AI
COPY run.sh run.sh
COPY src src
RUN apt-get update && apt-get install -y python3.9 python3-pip
RUN pip3 install --no-cache-dir -r src/requirements.txt
RUN chmod a+x run.sh
EXPOSE 8501
USER app
CMD ["./run.sh"]