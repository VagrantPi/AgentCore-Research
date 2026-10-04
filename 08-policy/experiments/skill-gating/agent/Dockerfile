# AgentCore Runtime 要 arm64，port 8080，提供 /ping 與 /invocations（由 bedrock-agentcore SDK 處理）
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 8080
CMD ["python", "main.py"]
