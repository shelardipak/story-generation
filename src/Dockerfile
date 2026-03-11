FROM python:3.9-slim
ARG DEBIAN_FRONTEND=noninteractive
RUN useradd -ms /bin/bash app
RUN mkdir /opt/qa-testgen-interactive-dashboard-AI
RUN chmod -R 777 /opt/qa-testgen-interactive-dashboard-AI
WORKDIR /opt/qa-testgen-interactive-dashboard-AI
COPY run.sh run.sh
COPY src src
RUN pip install --no-cache-dir -r src/requirements.txt
RUN chmod a+x run.sh
EXPOSE 80
USER app
CMD ["./run.sh"]